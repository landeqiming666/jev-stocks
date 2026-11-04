from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sentinel.semantic.segment import PassageSplit, TextSpan, split_passages, split_sentences

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "semantic" / "segment"


def _assert_exact(text: str, spans: list[TextSpan]) -> None:
    previous_end = 0
    for span in spans:
        assert previous_end <= span.start < span.end <= len(text)
        assert span.text == text[span.start : span.end]
        assert span.end - span.start == len(span.text)
        assert span.text == span.text.strip()
        previous_end = span.end


def test_split_sentences_handles_inc_and_decimal() -> None:
    text = "Zenith Arc Robotics Inc. rose 3.5 percent. Atlas sold shares."
    assert split_sentences(text) == [
        TextSpan(0, 42, "Zenith Arc Robotics Inc. rose 3.5 percent."),
        TextSpan(43, 61, "Atlas sold shares."),
    ]


def test_split_sentences_handles_chinese_punctuation() -> None:
    assert split_sentences("公司公告。控股股东拟减持！") == [
        TextSpan(0, 5, "公司公告。"),
        TextSpan(5, 13, "控股股东拟减持！"),
    ]


def test_split_sentences_keeps_closing_quote() -> None:
    assert split_sentences('He said "no." Then left.') == [
        TextSpan(0, 13, 'He said "no."'),
        TextSpan(14, 24, "Then left."),
    ]


def test_split_sentences_uses_paragraph_break_without_punctuation() -> None:
    assert split_sentences("Heading\n\nBody text") == [
        TextSpan(0, 7, "Heading"),
        TextSpan(9, 18, "Body text"),
    ]


def test_every_sentence_is_exact_original_substring() -> None:
    text = (FIXTURES / "e1_passage.txt").read_text(encoding="utf-8")
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    sentences = split_sentences(text)
    assert sentences == [TextSpan(**span) for span in cases["e1"]["sentences"]]
    _assert_exact(text, sentences)


def test_split_passages_never_exceeds_1200_chars() -> None:
    text = "x " * 900
    result = split_passages(text)
    assert result.passages == [
        TextSpan(0, 1199, "x " * 599 + "x"),
        TextSpan(1200, 1799, "x " * 299 + "x"),
    ]
    assert all(len(span.text) <= 1200 for span in result.passages)
    assert result.original_chars == 1800
    assert result.truncated is False
    _assert_exact(text, result.passages)


def test_split_passages_prefers_paragraph_boundary() -> None:
    text = "First sentence.\n\nSecond sentence."
    assert split_passages(text) == PassageSplit(
        [TextSpan(0, 15, "First sentence."), TextSpan(17, 33, "Second sentence.")],
        False,
        33,
    )


def test_split_passages_hard_splits_one_long_sentence() -> None:
    text = "a" * 2500
    result = split_passages(text)
    assert result == PassageSplit(
        [
            TextSpan(0, 1200, "a" * 1200),
            TextSpan(1200, 2400, "a" * 1200),
            TextSpan(2400, 2500, "a" * 100),
        ],
        False,
        2500,
    )
    _assert_exact(text, result.passages)


def test_split_passages_stops_at_60_and_sets_truncated() -> None:
    text = "\n\n".join(["abcdefghijklmnopqrst"] * 70)
    result = split_passages(text)
    assert len(result.passages) == 60
    assert result.passages[0] == TextSpan(0, 20, "abcdefghijklmnopqrst")
    assert result.passages[-1] == TextSpan(1298, 1318, "abcdefghijklmnopqrst")
    assert result.truncated is True
    assert result.original_chars == 1538
    _assert_exact(text, result.passages)


def test_split_passages_empty_text() -> None:
    assert split_passages("") == PassageSplit([], False, 0)


def test_split_passages_rejects_out_of_range_limits() -> None:
    with pytest.raises(ValueError, match="^max_chars$"):
        split_passages("Text.", max_chars=99)
    with pytest.raises(ValueError, match="^max_passages$"):
        split_passages("Text.", max_passages=61)


def test_e1_passage_offsets_match_fixture() -> None:
    text = (FIXTURES / "e1_passage.txt").read_text(encoding="utf-8")
    cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert (sentences[1].start, sentences[1].end) == (24, 265)
    assert sentences[1] == TextSpan(**cases["e1"]["sentences"][1])
    assert "completed the sale of 4.5%" in sentences[1].text
    assert text.endswith(".\n")
    assert len(text) == cases["e1"]["original_chars"] == 419
    assert split_passages(text) == PassageSplit([TextSpan(0, 418, text[:-1])], False, 419)


@pytest.mark.parametrize("text", ["", " \t\n\n", "\u3000\u00a0", "\n\n\n"])
def test_splitters_return_no_spans_for_whitespace(text: str) -> None:
    assert split_sentences(text) == []
    assert split_passages(text) == PassageSplit([], False, len(text))


@pytest.mark.parametrize("text", [None, 123, 3.5, True, False, b"Text.", ["Text."]])
def test_splitters_reject_non_string_text(text: object) -> None:
    with pytest.raises(ValueError, match="^text$"):
        split_sentences(cast(str, text))
    with pytest.raises(ValueError, match="^text$"):
        split_passages(cast(str, text))


@pytest.mark.parametrize("limit", [None, "100", 100.0, True, False, [], 0, 99, 1201])
def test_split_passages_rejects_invalid_max_chars(limit: object) -> None:
    with pytest.raises(ValueError, match="^max_chars$"):
        split_passages("", max_chars=cast(int, limit))


@pytest.mark.parametrize("limit", [None, "1", 1.0, True, False, [], 0, -1, 61])
def test_split_passages_rejects_invalid_max_passages(limit: object) -> None:
    with pytest.raises(ValueError, match="^max_passages$"):
        split_passages("", max_passages=cast(int, limit))


@pytest.mark.parametrize(
    ("abbreviation", "end"),
    [
        ("Mr.", 15),
        ("Mrs.", 16),
        ("Ms.", 15),
        ("Dr.", 15),
        ("Prof.", 17),
        ("Inc.", 16),
        ("Corp.", 17),
        ("Ltd.", 16),
        ("Co.", 15),
        ("LLC.", 16),
        ("PLC.", 16),
        ("No.", 15),
        ("vs.", 15),
        ("U.S.", 16),
        ("U.K.", 16),
        ("e.g.", 16),
        ("i.e.", 16),
        ("Item.", 17),
    ],
)
def test_split_sentences_preserves_fixed_abbreviations(abbreviation: str, end: int) -> None:
    text = f"{abbreviation} Adams left. Next."
    assert split_sentences(text) == [
        TextSpan(0, end, f"{abbreviation} Adams left."),
        TextSpan(end + 1, end + 6, "Next."),
    ]


def test_split_sentences_preserves_uppercase_multi_dot_abbreviations() -> None:
    assert split_sentences("E.G. Atlas rose. U.S. rose.") == [
        TextSpan(0, 16, "E.G. Atlas rose."),
        TextSpan(17, 27, "U.S. rose."),
    ]


def test_split_sentences_uses_unicode_codepoint_offsets() -> None:
    text = " \tA😀. Revenue fell.\n\n𠮷公司公告。盈利3.5%。\n"
    expected = [
        TextSpan(2, 5, "A😀."),
        TextSpan(6, 19, "Revenue fell."),
        TextSpan(21, 27, "𠮷公司公告。"),
        TextSpan(27, 34, "盈利3.5%。"),
    ]
    assert split_sentences(text) == expected
    _assert_exact(text, expected)
    assert split_passages(text) == PassageSplit(
        [TextSpan(2, 19, "A😀. Revenue fell."), TextSpan(21, 34, "𠮷公司公告。盈利3.5%。")],
        False,
        35,
    )
    assert split_sentences("A😀. Revenue fell.")[1] == TextSpan(4, 17, "Revenue fell.")


def test_split_sentences_absorbs_adjacent_closers_before_uppercase() -> None:
    assert split_sentences('A.")]}Next.') == [TextSpan(0, 6, 'A.")]}'), TextSpan(6, 11, "Next.")]
    assert split_sentences("公告。”）】」』Next.") == [
        TextSpan(0, 8, "公告。”）】」』"),
        TextSpan(8, 13, "Next."),
    ]


def test_split_sentences_keeps_consecutive_punctuation_together() -> None:
    assert split_sentences("Wait?!...Next!！Stop。") == [
        TextSpan(0, 9, "Wait?!..."),
        TextSpan(9, 15, "Next!！"),
        TextSpan(15, 20, "Stop。"),
    ]


@pytest.mark.parametrize(
    "initial",
    [
        "Next",
        "9",
        '"Next',
        "'Next",
        "“Next",
        "（Next",
        "(Next",
        "[Next",
        "公司",
        "𠮷社",
        "カナ",
        "한글",
    ],
)
def test_split_sentences_accepts_documented_sentence_starters(initial: str) -> None:
    text = f"A. \t{initial}"
    assert split_sentences(text) == [TextSpan(0, 2, "A."), TextSpan(4, len(text), initial)]


def test_split_sentences_does_not_split_before_lowercase() -> None:
    assert split_sentences("A. lower? still! yes。")[0] == TextSpan(0, 21, "A. lower? still! yes。")


def test_split_sentences_only_protects_ascii_decimal_digits() -> None:
    assert split_sentences("3.5 rose. ３.公司公告。") == [
        TextSpan(0, 9, "3.5 rose."),
        TextSpan(10, 12, "３."),
        TextSpan(12, 17, "公司公告。"),
    ]


def test_splitters_preserve_internal_whitespace_and_controls() -> None:
    text = " \tA\x00  B.\t\nC\t D.  "
    assert split_sentences(text) == [TextSpan(2, 8, "A\x00  B."), TextSpan(10, 15, "C\t D.")]
    assert split_passages(text) == PassageSplit([TextSpan(2, 15, "A\x00  B.\t\nC\t D.")], False, 17)


def test_splitters_skip_empty_double_newline_segments() -> None:
    text = " \n\nHead\n\n\n\n \tBody\n\n  "
    expected = [TextSpan(3, 7, "Head"), TextSpan(13, 17, "Body")]
    assert split_sentences(text) == expected
    assert split_passages(text) == PassageSplit(expected, False, 21)


@pytest.mark.parametrize(("count", "truncated"), [(60, False), (61, True)])
def test_split_passages_distinguishes_60_and_61_paragraphs(count: int, truncated: bool) -> None:
    text = "\n\n".join(["段😀"] * count) + " \t\n\n"
    result = split_passages(text)
    assert len(result.passages) == 60
    assert result.passages[-1] == TextSpan(236, 238, "段😀")
    assert result.truncated is truncated
    assert result.original_chars == len(text)
    _assert_exact(text, result.passages)


@pytest.mark.parametrize(("count", "lengths"), [(1200, [1200]), (1201, [1200, 1])])
def test_split_passages_distinguishes_1200_and_1201_codepoints(
    count: int, lengths: list[int]
) -> None:
    result = split_passages("😀" * count)
    assert [len(span.text) for span in result.passages] == lengths
    assert result.passages[0] == TextSpan(0, 1200, "😀" * 1200)
    if count == 1201:
        assert result.passages[1] == TextSpan(1200, 1201, "😀")
    assert result == split_passages("😀" * count)
    assert result.truncated is False


@pytest.mark.parametrize("suffix", ["", " \t\n\n\u3000", " Next."])
def test_split_passages_checks_unprocessed_nonwhitespace_after_limit(suffix: str) -> None:
    text = "a" * 1200 + suffix
    result = split_passages(text, max_passages=1)
    assert result.passages == [TextSpan(0, 1200, "a" * 1200)]
    assert result.truncated is bool(suffix.strip())
    assert result.original_chars == len(text)


def test_split_passages_truncates_inside_one_long_sentence() -> None:
    result = split_passages("a" * 1201, max_passages=1)
    assert result == PassageSplit([TextSpan(0, 1200, "a" * 1200)], True, 1201)


def test_split_passages_stops_inside_61_hard_chunks() -> None:
    result = split_passages("😀" * 6001, max_chars=100)
    assert len(result.passages) == 60
    assert result.passages[-1] == TextSpan(5900, 6000, "😀" * 100)
    assert result.truncated is True
    assert result.original_chars == 6001


@pytest.mark.parametrize("separator", [" ", "\t", "\n"])
def test_split_passages_hard_split_uses_last_whitespace_in_window(separator: str) -> None:
    text = "a" * 60 + separator + "b" * 29 + separator + "c" * 30
    result = split_passages(text, max_chars=100)
    assert result == PassageSplit(
        [TextSpan(0, 90, "a" * 60 + separator + "b" * 29), TextSpan(91, 121, "c" * 30)],
        False,
        121,
    )
    _assert_exact(text, result.passages)


@pytest.mark.parametrize(("position", "end"), [(49, 100), (50, 50), (100, 100)])
def test_split_passages_hard_split_whitespace_search_bounds(position: int, end: int) -> None:
    text = "a" * position + " " + "b" * (150 - position)
    result = split_passages(text, max_chars=100)
    assert result.passages[0].end == end
    assert result.passages[0].text == text[:end]
    assert result.truncated is False
    _assert_exact(text, result.passages)


def test_split_passages_merges_sentences_until_combined_length_limit() -> None:
    text = "a" * 59 + ". " + "B" * 37 + ". " + "C."
    assert split_passages(text, max_chars=100) == PassageSplit(
        [TextSpan(0, 99, "a" * 59 + ". " + "B" * 37 + "."), TextSpan(100, 102, "C.")],
        False,
        102,
    )


def test_split_passages_keeps_short_tail_of_hard_split_available_for_merging() -> None:
    text = "a" * 120 + ". Next."
    assert split_passages(text, max_chars=100) == PassageSplit(
        [TextSpan(0, 100, "a" * 100), TextSpan(100, 127, "a" * 20 + ". Next.")], False, 127
    )


def test_split_sentences_handles_long_dotted_token() -> None:
    text = "a." * 50000 + "End."
    assert split_sentences(text) == [
        TextSpan(0, 100000, "a." * 50000),
        TextSpan(100000, 100004, "End."),
    ]
