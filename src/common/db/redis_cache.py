import json
import pickle
from typing import Any, Optional

import redis
from config.settings import settings


_client: Optional[redis.Redis] = None


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _client


class RedisCache:
    def __init__(self) -> None:
        self.client = get_redis_client()

    def get(self, key: str) -> Optional[Any]:
        try:
            data = self.client.get(key)
            if data is None:
                return None
            return pickle.loads(data)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            serialized = pickle.dumps(value)
            if ttl:
                self.client.setex(key, ttl, serialized)
            else:
                self.client.set(key, serialized)
        except Exception:
            pass

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except Exception:
            pass

    def get_json(self, key: str) -> Optional[Any]:
        try:
            data = self.client.get(key)
            if data is None:
                return None
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            serialized = json.dumps(value, default=str).encode("utf-8")
            if ttl:
                self.client.setex(key, ttl, serialized)
            else:
                self.client.set(key, serialized)
        except Exception:
            pass

    def lpush_trim(self, key: str, value: Any, max_len: int, ttl: Optional[int] = None) -> None:
        try:
            serialized = json.dumps(value, default=str).encode("utf-8")
            pipe = self.client.pipeline()
            pipe.lpush(key, serialized)
            pipe.ltrim(key, 0, max_len - 1)
            if ttl:
                pipe.expire(key, ttl)
            pipe.execute()
        except Exception:
            pass

    def lrange_json(self, key: str, start: int = 0, end: int = -1) -> list:
        try:
            items = self.client.lrange(key, start, end)
            return [json.loads(item.decode("utf-8")) for item in items]
        except Exception:
            return []

    def hget_json(self, key: str, field: str) -> Optional[Any]:
        try:
            data = self.client.hget(key, field)
            if data is None:
                return None
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def hset_json(self, key: str, field: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            serialized = json.dumps(value, default=str).encode("utf-8")
            self.client.hset(key, field, serialized)
            if ttl:
                self.client.expire(key, ttl)
        except Exception:
            pass


redis_cache = RedisCache()
