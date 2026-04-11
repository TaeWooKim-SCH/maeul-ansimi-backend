from typing import Any, Callable

from django.core.cache import cache


def get_or_set(key: str, callback: Callable[[], Any], timeout: int) -> Any:
    """캐시에서 값을 가져오고, 없으면 callback 실행 후 저장."""
    value = cache.get(key)
    if value is None:
        value = callback()
        cache.set(key, value, timeout)
    return value


def invalidate(key: str) -> None:
    """캐시 키 삭제."""
    cache.delete(key)
