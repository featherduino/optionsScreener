import redis
from app.config import CACHE_ENABLED, REDIS_URL

r = None
if CACHE_ENABLED:
    r = redis.Redis.from_url(REDIS_URL)

def cache_set(key, value, ttl=30):
    if r:
        r.set(key, value, ex=ttl)

def cache_get(key):
    if r:
        return r.get(key)
    return None
