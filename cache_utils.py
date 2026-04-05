# cache_utils.py - WITH PROPER FALLBACK
from flask import current_app, request
import hashlib
from functools import wraps
import time
from flask_login import current_user


class SimpleDictCache:
    """Simple dictionary-based cache as fallback"""

    def __init__(self):
        self._cache = {}
        self._timestamps = {}

    def get(self, key):
        if key in self._cache:
            timestamp = self._timestamps.get(key, 0)
            # Default timeout of 300 seconds
            if time.time() - timestamp < 300:
                return self._cache[key]
            else:
                # Expired, clean up
                del self._cache[key]
                del self._timestamps[key]
        return None

    def set(self, key, value, timeout=None):
        self._cache[key] = value
        self._timestamps[key] = time.time()

        # Simple cleanup if we have too many items
        if len(self._cache) > 1000:
            # Remove oldest 100 items
            sorted_keys = sorted(self._timestamps.items(), key=lambda x: x[1])
            for old_key, _ in sorted_keys[:100]:
                if old_key in self._cache:
                    del self._cache[old_key]
                if old_key in self._timestamps:
                    del self._timestamps[old_key]

    def delete(self, key):
        if key in self._cache:
            del self._cache[key]
        if key in self._timestamps:
            del self._timestamps[key]

    def clear(self):
        self._cache.clear()
        self._timestamps.clear()


# Global simple cache as fallback
_simple_fallback_cache = SimpleDictCache()


def get_cache():
    """Get cache instance with fallback"""
    if not current_app:
        return _simple_fallback_cache

    # Try to get Flask-Caching cache
    cache_ext = current_app.extensions.get("cache")

    if cache_ext is None:
        # No cache extension, use simple fallback
        return _simple_fallback_cache

    # Flask-Caching stores cache instances differently
    # Try to get the actual cache object
    try:
        # Flask-Caching v2.x structure
        if hasattr(cache_ext, "cache"):
            return cache_ext.cache
        # Flask-Caching v1.x or different structure
        elif isinstance(cache_ext, dict):
            # Sometimes it's a dict with cache instances
            for key, value in cache_ext.items():
                if hasattr(value, "get") and hasattr(value, "set"):
                    return value
            # If no proper cache found in dict, use fallback
            return _simple_fallback_cache
        else:
            # Assume it's the cache object itself
            return cache_ext
    except:
        # If anything goes wrong, use simple fallback
        return _simple_fallback_cache


def cache_response(timeout=300, key_prefix="api_"):
    """Safe cache decorator with automatic fallback"""

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache = get_cache()

            # Generate cache key
            request_signature = {
                "path": getattr(request, "path", ""),
                "query": sorted((request.args or {}).items(multi=True))
                if request
                else [],
                "user_id": (
                    getattr(current_user, "id", None)
                    if getattr(current_user, "is_authenticated", False)
                    else None
                ),
                "kwargs": kwargs,
            }
            cache_key = (
                f"{key_prefix}{f.__name__}_"
                f"{hashlib.md5(str(request_signature).encode()).hexdigest()}"
            )

            # Try to get from cache
            try:
                cached_data = cache.get(cache_key)
                if cached_data is not None:
                    if current_app:
                        current_app.logger.debug(f"Cache hit: {cache_key}")
                    return cached_data
            except Exception as e:
                if current_app:
                    current_app.logger.debug(
                        f"Cache get failed, will compute fresh: {e}"
                    )

            # Execute function
            result = f(*args, **kwargs)

            # Cache the result
            try:
                cache.set(cache_key, result, timeout=timeout)
                if current_app:
                    current_app.logger.debug(f"Cached result: {cache_key}")
            except Exception as e:
                if current_app:
                    current_app.logger.debug(f"Cache set failed (non-critical): {e}")

            return result

        return decorated_function

    return decorator


# Keep other functions but update them to use get_cache()
def invalidate_cache(pattern):
    """Invalidate cache - simple pattern matching for dict cache"""
    cache = get_cache()

    if hasattr(cache, "delete"):
        # Exact key deletion
        if not pattern.endswith("*"):
            try:
                cache.delete(pattern)
                if current_app:
                    current_app.logger.debug(f"Invalidated: {pattern}")
            except:
                pass
        else:
            # Pattern matching for simple cache
            pattern_prefix = pattern.rstrip("*")
            if isinstance(cache, SimpleDictCache):
                keys_to_delete = [
                    k for k in cache._cache.keys() if k.startswith(pattern_prefix)
                ]
                for key in keys_to_delete:
                    cache.delete(key)
                if current_app and keys_to_delete:
                    current_app.logger.debug(
                        f"Invalidated {len(keys_to_delete)} keys matching: {pattern}"
                    )


def clear_user_cache(user_id):
    """Clear all cache for a specific user"""
    patterns = [
        f"dashboard_stats_{user_id}_",
        f"api_dashboard_stats_{user_id}_",
        f"api_dashboard_reviews_{user_id}_",
        f"api_dashboard_services_{user_id}_",
    ]

    for pattern in patterns:
        invalidate_cache(f"{pattern}*")
