import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, TypeVar


def make_tree(
    paths: Iterable[str], strip_prefix: str | None = None
) -> dict[str, Any]:
    type Node = defaultdict[Any, Any]

    def tree() -> Node:
        return defaultdict(tree)

    root = tree()
    if strip_prefix:
        paths = [
            p[len(strip_prefix) :] if p.startswith(strip_prefix) else p
            for p in paths
        ]
    for path in paths:
        node = root
        for part in path.split("/"):
            node = node[part]

    # convert defaultdicts to plain dicts for Jinja
    def to_dict(d: Node) -> dict[str, Any]:
        return {k: to_dict(v) if v else {} for k, v in d.items()}

    return to_dict(root)


T = TypeVar("T")


def cache_for(
    duration: int = 600,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        cache: dict[tuple[Any, ...], tuple[T, float]] = {}

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            key = (args, frozenset(kwargs.items()))
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < duration:
                    return result
            result = func(*args, **kwargs)
            cache[key] = (result, time.time())
            return result

        return wrapper

    return decorator
