import logging
import re
import unicodedata

from selectolax.lexbor import LexborHTMLParser

from sentinel.logging_setup import get_logger, log_event

MAX_TEXT_CHARS = 200000
_BLOCKS = "p, div, br, li, tr, h1, h2, h3, h4, h5, h6, table, section"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text).replace("\xa0", " ")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def html_to_text(html: str) -> str:
    if not html:
        return ""
    try:
        # scripting 只改变 HTML 分词，避免 head 内 noscript 文本被移到 body；不会执行脚本。
        tree = LexborHTMLParser(html, scripting=True)
        for node in tree.css("script, style, noscript"):
            node.decompose()
        for node in tree.css("head"):
            node.decompose()
        for node in tree.css(_BLOCKS):
            node.insert_before("\n")
            node.insert_after("\n")
        for node in tree.css("td, th"):
            next_cell = node.next
            while next_cell is not None and next_cell.tag == "-text":
                next_cell = next_cell.next
            if next_cell is not None and next_cell.tag in {"td", "th"}:
                node.insert_after(" | ")
        text = normalize_text(tree.text())
    except (ValueError, TypeError, RuntimeError):
        log_event(get_logger(__name__), logging.WARNING, event="sec.html_parse_failed")
        return ""
    if len(text) > MAX_TEXT_CHARS:
        log_event(
            get_logger(__name__),
            logging.WARNING,
            event="sec.text_truncated",
            max_chars=MAX_TEXT_CHARS,
        )
    return text[:MAX_TEXT_CHARS]
