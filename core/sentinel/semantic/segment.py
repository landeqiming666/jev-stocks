from __future__ import annotations

from dataclasses import dataclass

MAX_PASSAGE_CHARS = 1200
MAX_PASSAGES_PER_DOCUMENT = 60
MIN_PASSAGE_CHARS = 100
ABBREVIATIONS = frozenset(
    [
        "mr.",
        "mrs.",
        "ms.",
        "dr.",
        "prof.",
        "inc.",
        "corp.",
        "ltd.",
        "co.",
        "llc.",
        "plc.",
        "no.",
        "vs.",
        "u.s.",
        "u.k.",
        "e.g.",
        "i.e.",
        "item.",
    ]
)
SENTENCE_END = ".?!。！？"
CLOSERS = "\"'”’)]}）】」』"
_MAX_ABBREVIATION_CHARS = max(map(len, ABBREVIATIONS))


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class PassageSplit:
    passages: list[TextSpan]
    truncated: bool
    original_chars: int


def _skip_whitespace(text: str, start: int, end: int) -> int:
    while start < end and text[start].isspace():
        start += 1
    return start


def _span(text: str, start: int, end: int) -> TextSpan | None:
    start = _skip_whitespace(text, start, end)
    while end > start and text[end - 1].isspace():
        end -= 1
    return TextSpan(start, end, text[start:end]) if start < end else None


def _is_token_character(char: str) -> bool:
    return char == "." or "a" <= char <= "z" or "A" <= char <= "Z"


def _is_abbreviation(text: str, dot: int) -> bool:
    start = dot
    while start > 0 and _is_token_character(text[start - 1]):
        start -= 1
        # 未知的超长点号 token 不可能匹配缩写表，避免重复扫描整串。
        if dot + 1 - start > _MAX_ABBREVIATION_CHARS:
            return False
    if text[start : dot + 1].lower() in ABBREVIATIONS:
        return True
    # U.S. 的第一个句点后也是大写字母，必须识别完整 token。
    end = dot + 1
    while end < len(text) and _is_token_character(text[end]):
        end += 1
        if end - start > _MAX_ABBREVIATION_CHARS:
            return False
    return text[start:end].lower() in ABBREVIATIONS


def _is_sentence_start(char: str) -> bool:
    codepoint = ord(char)
    return (
        char.isupper()
        or char.isdigit()
        or char in "\"'“（(["
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x323AF
        or 0x3040 <= codepoint <= 0x30FF
        or 0x31F0 <= codepoint <= 0x31FF
        or 0x1100 <= codepoint <= 0x11FF
        or 0x3130 <= codepoint <= 0x318F
        or 0xA960 <= codepoint <= 0xA97F
        or 0xAC00 <= codepoint <= 0xD7FF
    )


def split_sentences(text: str) -> list[TextSpan]:
    if not isinstance(text, str):
        raise ValueError("text")

    sentences: list[TextSpan] = []
    limit = len(text)
    start = _skip_whitespace(text, 0, limit)
    i = start
    while i < limit:
        if text.startswith("\n\n", i):
            sentence = _span(text, start, i)
            if sentence is not None:
                sentences.append(sentence)
            start = _skip_whitespace(text, i + 2, limit)
            i = start
            continue

        if text[i] not in SENTENCE_END:
            i += 1
            continue
        if text[i] == "." and (
            (i > 0 and i + 1 < limit and "0" <= text[i - 1] <= "9" and "0" <= text[i + 1] <= "9")
            # 闭引号内的 no. 也能结束句子（§8.1），闭合符优先于缩写例外。
            or (_is_abbreviation(text, i) and (i + 1 == limit or text[i + 1] not in CLOSERS))
        ):
            i += 1
            continue

        # 连续标点和闭合符属于前句，不能把闭引号当作后一句的开引号。
        end = i + 1
        while end < limit and text[end] in SENTENCE_END + CLOSERS:
            end += 1
        following = _skip_whitespace(text, end, limit)
        if following == limit or _is_sentence_start(text[following]):
            sentence = _span(text, start, end)
            if sentence is not None:
                sentences.append(sentence)
            start = following
        i = end

    sentence = _span(text, start, limit)
    if sentence is not None:
        sentences.append(sentence)
    return sentences


def _limited_result(text: str, passages: list[TextSpan]) -> PassageSplit:
    # 达到数量上限不等于丢失内容；段间或末尾空白不算未处理正文。
    remaining = _skip_whitespace(text, passages[-1].end, len(text))
    return PassageSplit(passages, remaining < len(text), len(text))


def split_passages(
    text: str,
    *,
    max_chars: int = MAX_PASSAGE_CHARS,
    max_passages: int = MAX_PASSAGES_PER_DOCUMENT,
) -> PassageSplit:
    if not isinstance(text, str):
        raise ValueError("text")
    if (
        not isinstance(max_chars, int)
        or isinstance(max_chars, bool)
        or not MIN_PASSAGE_CHARS <= max_chars <= MAX_PASSAGE_CHARS
    ):
        raise ValueError("max_chars")
    if (
        not isinstance(max_passages, int)
        or isinstance(max_passages, bool)
        or not 1 <= max_passages <= MAX_PASSAGES_PER_DOCUMENT
    ):
        raise ValueError("max_passages")

    passages: list[TextSpan] = []
    pending: TextSpan | None = None
    for sentence in split_sentences(text):
        if pending is not None:
            if (
                "\n\n" in text[pending.end : sentence.start]
                or sentence.end - pending.start > max_chars
            ):
                passages.append(pending)
                if len(passages) == max_passages:
                    return _limited_result(text, passages)
                pending = None
            else:
                pending = TextSpan(pending.start, sentence.end, text[pending.start : sentence.end])
                continue

        start = sentence.start
        while sentence.end - start > max_chars:
            end = start + max_chars
            for position in range(end, start + max_chars // 2 - 1, -1):
                if text[position] in " \t\n":
                    end = position
                    break
            fragment = _span(text, start, end)
            if fragment is not None:
                passages.append(fragment)
                if len(passages) == max_passages:
                    return _limited_result(text, passages)
            start = _skip_whitespace(text, end, sentence.end)
        pending = _span(text, start, sentence.end)

    if pending is not None:
        passages.append(pending)
    return PassageSplit(passages, False, len(text))
