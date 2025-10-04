import re
from collections.abc import Iterable
from typing import Any, cast

from marko import HTMLRenderer, Markdown, block, inline
from marko.block import HTMLBlock
from marko.ext.gfm import GFM
from marko.helpers import MarkoExtension, render_dispatch
from marko.source import Source
from pygments import highlight
from pygments.formatters import html
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.util import ClassNotFound

from trx_website.utils import make_tree, parse_fancy_tree


def render_jinjax(element: str, **ctx: Any) -> str:
    # This makes me cry but it's not me who decided to architect the entire
    # package as a collection of stateless singletons
    from trx_website.templating import catalog

    return cast(str, catalog.irender(element, **ctx))


class FileTreeBlock(HTMLBlock):
    priority = 6

    @classmethod
    def match(cls, source: Source) -> int | bool:
        source.context.html_end = None
        if source.expect_re(r"(?i) {,3}<details data-id=\"file-tree.*\">"):
            assert source.match
            source.context.html_end = re.compile(r"(?i)</details>")
            return 1
        return False


class Alert(block.Quote):
    """
    Alert block element: block quote with a header like WARNING, NOTE, TIP,
    IMPORTANT, or CAUTION.
    """

    priority = block.Quote.priority + 1

    def __init__(self, alert_type: str) -> None:
        self.alert_type = alert_type

    @classmethod
    def match(cls, source: Any) -> Any:
        return source.expect_re(
            r" {,3}>\s*\[\!(WARNING|NOTE|TIP|IMPORTANT|CAUTION)\]"
        )

    @classmethod
    def parse(cls, source: Any) -> Any:
        m = source.match
        admon_type = m.group(1)
        source.next_line(require_prefix=False)
        source.consume()
        state = cls(admon_type)
        with source.under_state(state):
            state.children = source.parser.parse_source(source)
        return state


class AlertRendererMixin:
    def render_alert(self, element: Alert) -> str:
        return render_jinjax(
            "Note",
            variant=element.alert_type.lower(),
            _content=self.render_children(element),  # type: ignore[attr-defined]
        )


class TRXRendererMixin:
    def render_file_tree_block(self, element: FileTreeBlock) -> str:
        fancy_tree_str: str = re.sub(
            "</?(pre|code|details)[^>]*>", "", element.body.strip()
        )
        paths = parse_fancy_tree(fancy_tree_str)
        return render_jinjax(
            "FileTree",
            tree=make_tree(paths),
            open_levels=2 if "file-tree-mac" in element.body else 1,
        )

    def render_link(self, element: inline.AutoLink) -> str:
        content: str = self.render_children(element)  # type: ignore[attr-defined]
        url: str = self.escape_url(element.dest)  # type: ignore[attr-defined]
        title: str | None = (
            self.escape_html(element.title)  # type: ignore[attr-defined]
            if element.title
            else None
        )
        if url.startswith(("https://", "http://")):
            return render_jinjax(
                "Link", title=title, href=url, _content=content
            )
        return cast(str, HTMLRenderer.render_link(self, element))

    def render_heading(self, element: block.Heading) -> str:
        return render_jinjax(
            "Heading",
            level=element.level,
            _content=self.render_children(element),  # type: ignore[attr-defined]
        )


def make_gfm_extra_extension() -> MarkoExtension:
    return MarkoExtension(
        elements=[Alert, FileTreeBlock],
        renderer_mixins=[AlertRendererMixin],
    )


def make_trx_extension() -> MarkoExtension:
    return MarkoExtension(
        elements=[],
        renderer_mixins=[TRXRendererMixin],
    )


class TypedCodeSpan(inline.InlineElement):
    """Inline code span: `code sample`"""

    priority = inline.CodeSpan.priority + 1
    pattern = re.compile(
        r"\[([a-z0-9]+)\](?<!`)(`+)(?!`)([\s\S]+?)(?<!`)\2(?!`)"
    )

    def __init__(self, match: re.Match[str]) -> None:
        self.lang = match.group(1)
        self.children = match.group(3).replace("\n", " ")
        if (
            self.children.strip()
            and self.children[0] == self.children[-1] == " "
        ):
            self.children = self.children[1:-1]


class InlineHtmlFormatter(html.HtmlFormatter):
    def __init__(self, **options: Any) -> None:
        default_opt = dict(
            cssclass="highlight inline", wrapcode=True, lineseparator=""
        )
        super().__init__(**{**default_opt, **options})

    def _wrap_pre(self, inner: Any) -> Iterable[Any]:
        yield from inner


class CodeHiliteInlineRendererMixin:
    @render_dispatch(HTMLRenderer)  # type: ignore[misc]
    def render_typed_code_span(self, element: TypedCodeSpan) -> str:
        code = cast(str, element.children)
        if element.lang:
            try:
                lexer = get_lexer_by_name(element.lang, stripall=True)
            except ClassNotFound:
                lexer = guess_lexer(code)
        else:
            lexer = guess_lexer(code)
        formatter = InlineHtmlFormatter()
        highlighted = highlight(code, lexer, formatter)
        return f"{highlighted}"


def make_code_hilite_inline_extension() -> MarkoExtension:
    return MarkoExtension(
        elements=[TypedCodeSpan],
        renderer_mixins=[CodeHiliteInlineRendererMixin],
    )


def render_markdown(md_text: str) -> str:
    md = Markdown(
        extensions=[
            make_trx_extension(),
            make_gfm_extra_extension(),
            make_code_hilite_inline_extension(),
            GFM,
            "codehilite",
        ]
    )
    html = cast(str, md.convert(md_text))
    return html
