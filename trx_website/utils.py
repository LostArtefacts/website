import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, TypeVar


def parse_fancy_tree(tree_str: str) -> Iterable[str]:
    lines = tree_str.splitlines()
    result = []
    stack: list[str] = []

    for i, raw_line in enumerate(lines):
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if "──" not in line:
            continue

        # get name
        name = line.split("──", 1)[1].strip()

        # calculate depth
        prefix = line.split("──", 1)[0]
        depth = len(prefix) // 4

        # trim stack
        stack = stack[:depth]

        # look ahead: is next line deeper?
        is_dir = False
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            if "──" in nxt:
                nxt_prefix = nxt.split("──", 1)[0]
                nxt_depth = len(nxt_prefix) // 4
                if nxt_depth > depth:
                    is_dir = True

        if is_dir:
            stack.append(name)  # push dir onto stack
        else:
            result.append("./" + "/".join(stack + [name]))

    return result


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

    def natural_sort_key(s: str) -> list[int | str]:
        return [
            int(text) if text.isdigit() else text.lower()
            for text in re.split(r"(\d+)", s)
        ]

    # convert defaultdicts to plain dicts for Jinja
    def to_dict(d: Node) -> dict[str, Any]:
        return {
            k: to_dict(v) if v else {}
            for k, v in sorted(
                d.items(),
                key=lambda x: (len(x[1]) == 0, natural_sort_key(x[0])),
            )
        }

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
