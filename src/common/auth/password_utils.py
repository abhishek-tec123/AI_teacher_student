from passlib.context import CryptContext
import os
import re
from typing import Optional

# Legacy AES decryption support (migration from old Fernet-encrypted passwords)
from cryptography.fernet import Fernet

_AES_KEY = os.environ.get("AES_KEY")
if not _AES_KEY:
    from config.settings import settings
    _AES_KEY = settings.aes_key

_fernet = Fernet(_AES_KEY.encode() if isinstance(_AES_KEY, str) else _AES_KEY) if _AES_KEY else None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _is_fernet_token(value: str) -> bool:
    """Detect legacy Fernet-encrypted passwords (e.g. gAAAAAB...)."""
    if not value or len(value) < 20:
        return False
    try:
        # Fernet tokens are base64url and decode to a specific envelope.
        # Quick heuristic: they start with 'gAAAAA' and contain no '$'.
        return value.startswith("gAAAAA") and "$" not in value
    except Exception:
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Supports both bcrypt hashes and legacy Fernet/AES-encrypted passwords.
    """
    if not hashed_password:
        return False

    # Handle legacy AES-encrypted passwords
    if _is_fernet_token(hashed_password):
        if _fernet is None:
            return False
        try:
            decrypted = _fernet.decrypt(hashed_password.encode()).decode()
            return decrypted == plain_password
        except Exception:
            return False

    # Standard bcrypt verification
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate password hash."""
    return pwd_context.hash(password)

def validate_password_strength(password: str) -> tuple[bool, Optional[str]]:
    """
    Validate password strength.
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"
    
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "Password must contain at least one special character"
    
    return True, None

def generate_default_password() -> str:
    """Generate a secure default password for new users (max 72 bytes for bcrypt)."""
    import secrets
    import string
    
    # Use a shorter but still secure password to stay within bcrypt's 72-byte limit
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Generate 16 characters which should be well within the limit
    password = ''.join(secrets.choice(alphabet) for _ in range(16))
    
    # Ensure password meets requirements and stays within limit
    attempts = 0
    while (not validate_password_strength(password)[0] or 
           len(password.encode('utf-8')) > 72) and attempts < 10:
        password = ''.join(secrets.choice(alphabet) for _ in range(16))
        attempts += 1
    
    # If still not valid, use a simpler but secure password
    if attempts >= 10:
        password = f"Temp{secrets.randbelow(100000):05d}!"
    
    return password
