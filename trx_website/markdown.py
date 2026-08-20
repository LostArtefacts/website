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
            "Card",
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

    def render_line_break(self, element: inline.LineBreak) -> str:
        if getattr(element, "ends_lead_in", False):
            return "<br />\n"
        return cast(str, HTMLRenderer.render_line_break(self, element))

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
    # The [lang] tag only counts as one when it opens the span - an index like
    # `trx.items[0]` sits mid-word, and letting it start a span would swallow
    # the rest of the code span and everything up to the next backtick.
    pattern = re.compile(
        r"(?<![\w`])\[([a-z0-9]+)\](?<!`)(`+)(?!`)([\s\S]+?)(?<!`)\2(?!`)"
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

    def _wrap_div(self, inner: Any) -> Iterable[Any]:
        # The default wrapper is a <div>, which is block level and so breaks
        # the line of the paragraph the span sits in.
        yield 0, f'<span class="{self.cssclass}">'
        yield from inner
        yield 0, "</span>"


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
        highlighted = cast(str, highlight(code, lexer, formatter))
        return highlighted.strip()


def make_code_hilite_inline_extension() -> MarkoExtension:
    return MarkoExtension(
        elements=[TypedCodeSpan],
        renderer_mixins=[CodeHiliteInlineRendererMixin],
    )


def mark_lead_ins(element: Any) -> None:
    """
    Flag the soft line break that ends a bold lead-in.

    The docs open many a paragraph with a bold lead-in on a line of its own,
    followed by the explanation, and mean the two to land on separate lines.
    Every other soft break is the source file's own hard wrap and keeps
    collapsing into a space, or the prose would render at whatever width the
    file happens to be wrapped to.
    """
    children = getattr(element, "children", None)
    if not isinstance(children, list):
        return
    for i, child in enumerate(children):
        mark_lead_ins(child)
        if not isinstance(child, inline.LineBreak) or not child.soft:
            continue
        if i < 1 or not isinstance(children[i - 1], inline.StrongEmphasis):
            continue
        if i == 1 or isinstance(children[i - 2], inline.LineBreak):
            child.ends_lead_in = True


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
    doc = md.parse(md_text)
    mark_lead_ins(doc)
    html = cast(str, md.render(doc))
    return html
