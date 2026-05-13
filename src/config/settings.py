from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging
logger = logging.getLogger(__name__)



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # App
    app_name: str = "Student Learning API"
    debug: bool = False
    environment: str = "production"

    # MongoDB
    mongodb_uri: str
    db_name: str = "tutor_ai"
    collection_name: Optional[str] = None

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None

    # JWT — derive from AES_KEY if not set (legacy compat)
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 180
    jwt_refresh_token_expire_days: int = 7

    # Legacy AES key (used as JWT fallback during migration)
    aes_key: Optional[str] = None

    # CORS
    cors_origins: str = "https://tecorb.in"

    # LLM / APIs
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    tavily_api_key: Optional[str] = None
    gemini_llm: str
    groq_llm: str

    # Primary LLM (Ollama / OpenAI-compatible)
    default_llm_model: str = "ollama/kimi-k2.6:cloud"
    ollama_api_key: Optional[str] = None
    ollama_base_url: str = "https://ollama.com/v1"

    # Embeddings / Models
    embed_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # TTS
    tts_default_voice: str = "en-US-AriaNeural"

    # Rate Limits
    rate_limit_admin_requests: int = 120
    rate_limit_teacher_requests: int = 120
    rate_limit_default_requests: int = 300
    rate_limit_window: int = 60

    # Groq LLM Rate Limits
    groq_tpm_limit: int = 29000  # Tokens per minute limit (slightly below 8000 to have headroom)
    groq_tpm_reserve: int = 500  # Reserve tokens for critical calls
    groq_max_concurrent: int = 2  # Max concurrent Groq API calls
    groq_retry_max_attempts: int = 3  # Max retries on 429 rate limit
    groq_retry_base_delay: float = 2.0  # Base delay in seconds for exponential backoff

    def model_post_init(self, __context):
        if not self.jwt_secret_key:
            if self.aes_key:
                logger.warning("JWT_SECRET_KEY not set; using AES_KEY as fallback. Please set JWT_SECRET_KEY in .env")
                object.__setattr__(self, "jwt_secret_key", self.aes_key)
            else:
                raise ValueError("JWT_SECRET_KEY is required. Set it in your .env file.")

    @property
    def cors_origins_list(self) -> List[str]:
        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if self.environment == "development":
            origins.extend(["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:3000"])
        return origins


settings = Settings()
