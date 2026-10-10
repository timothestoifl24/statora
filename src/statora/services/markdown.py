import markdown as md
import nh3

_ALLOWED_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "blockquote",
    "h3",
    "h4",
    "hr",
}


def render_markdown(text: str) -> str:
    """Markdown to HTML, sanitised so incident text can't inject markup into public pages."""
    if not text:
        return ""
    html = md.markdown(text, extensions=["sane_lists"])
    return nh3.clean(
        html, tags=_ALLOWED_TAGS, attributes={"a": {"href", "title"}}, link_rel="noopener nofollow"
    )
