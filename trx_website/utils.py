import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

from trx_website.settings import STATIC_DIR


def get_file_listing(name: str) -> Iterable[str]:
    def recurse(name: str) -> Iterable[str]:
        for line in (STATIC_DIR / name).read_text().splitlines():
            if match := re.match(r"(.*){(.+)}(.*)", line):
                prefix, subname, suffix = match.groups()
                for subline in get_file_listing(
                    f"{Path(name).parent}/{subname}.txt"
                ):
                    yield "./" + str(Path(f"{prefix}{subline}{suffix}"))
            else:
                yield "./" + str(Path(line))

    return sorted(recurse(name), key=lambda line: (line.count("/"), line))


def make_tree_string(paths: list[str], strip_prefix: str | None = None) -> str:
    # optionally strip a prefix like "Contents/Resources/"
    if strip_prefix:
        paths = [
            p[len(strip_prefix) :] if p.startswith(strip_prefix) else p
            for p in paths
        ]

    type Node = defaultdict[Any, Any]

    # build nested dict
    def tree() -> Node:
        return defaultdict(tree)

    root = tree()
    for path in paths:
        node = root
        for part in path.split("/"):
            node = node[part]

    # recursive render
    def render(node: Node, prefix: str = "") -> list[str]:
        entries = sorted(node.keys())
        lines = []
        for i, name in enumerate(entries):
            last = i == len(entries) - 1
            branch = "└── " if last else "├── "
            subprefix = "    " if last else "│   "
            lines.append(prefix + branch + name)
            if node[name]:
                lines.extend(render(node[name], prefix + subprefix))
        return lines

    return ".\n" + "\n".join(render(root))


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
