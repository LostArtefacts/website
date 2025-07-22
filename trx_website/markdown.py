from typing import Any, cast

from marko import Markdown, block, inline
from marko.ext.gfm import GFM
from marko.helpers import MarkoExtension, render_dispatch
from marko.html_renderer import HTMLRenderer
from marko.md_renderer import MarkdownRenderer


def render_jinjax(element: str, **ctx: Any) -> str:
    # This makes me cry but it's not me who decided to architect the entire
    # package as a collection of stateless singletons
    from trx_website.templating import catalog

    return cast(str, catalog.irender(element, **ctx))


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
    @render_dispatch(HTMLRenderer)
    def render_alert(self, element):
        return render_jinjax(
            "Note",
            variant=element.alert_type.lower(),
            _content=self.render_children(element),
        )

    @render_alert.dispatch(MarkdownRenderer)  # type: ignore[no-redef]
    def render_alert(self, element):
        lines: list[str] = []
        lines.append(self._prefix + f"> [!{element.alert_type}]\n")
        with self.container("> ", "> "):
            for child in element.children:
                lines.append(self.render(child))
        self._prefix = self._second_prefix
        return "".join(lines)


class TRXRendererMixin:
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
        elements=[Alert],
        renderer_mixins=[AlertRendererMixin],
    )


def make_trx_extension() -> MarkoExtension:
    return MarkoExtension(
        elements=[],
        renderer_mixins=[TRXRendererMixin],
    )


def render_markdown(md_text: str) -> str:
    md = Markdown(
        extensions=[make_trx_extension(), make_gfm_extra_extension(), GFM]
    )
    html = cast(str, md.convert(md_text))
    return html
