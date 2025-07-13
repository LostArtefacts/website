import re
import unicodedata
from datetime import date, datetime
from typing import Any
from uuid import uuid4

from jinjax import Catalog

from trx_website.markdown import render_markdown
from trx_website.settings import ROOT_DIR
from trx_website.utils import cache_for

_slugify_invalid_chars_re = re.compile(r"[^\w\s-]")
_slugify_whitespace_re = re.compile(r"[\s]+")


def unique_id(content: Any | None = None) -> str:
    """Generate an HTML id: random UUID if no content."""
    return str(uuid4())


def slugify(content: Any) -> str:
    """Generate an HTML id: a GitHub-style slug."""
    if isinstance(content, str):
        content_str = content
    else:
        try:
            content_str = content()
        except Exception:
            content_str = str(content)

    if not content_str:
        return str(uuid4())

    text = unicodedata.normalize("NFKD", content_str)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()

    text = _slugify_invalid_chars_re.sub("", text)
    text = _slugify_whitespace_re.sub("-", text).strip("-")

    return text


@cache_for(duration=600)
def markdown(text: str) -> str:
    return render_markdown(text)


def format_datetime(value: datetime | date) -> str:
    format = "%b %d, %Y"
    return value.strftime(format)


catalog = Catalog(
    globals=dict(slugify=slugify, unique_id=unique_id),
    filters=dict(markdown=markdown, format_datetime=format_datetime),
)
catalog.add_folder(ROOT_DIR / "templates")
catalog.add_folder(ROOT_DIR / "templates/pages")
catalog.add_folder(ROOT_DIR / "templates/icons")
