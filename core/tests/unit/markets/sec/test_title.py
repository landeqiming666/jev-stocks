from sentinel.markets.sec.title import build_title


def test_build_title_8k_uses_item_names():
    assert build_title(
        form_type="8-K", items="2.02,9.01", primary_doc_description=None, first_line=None
    ) == ("8-K: Results of Operations and Financial Condition；Financial Statements and Exhibits")


def test_build_title_unknown_and_6k_truncate():
    assert "Item 99.99" in build_title(
        form_type="8-K/A", items="99.99", primary_doc_description=None, first_line=None
    )
    title = build_title(
        form_type="6-K", items=None, primary_doc_description=None, first_line="a" * 200
    )
    assert title.startswith("6-K: ") and len(title) <= 120


def test_title_limit_includes_prefix_and_nfc_and_fallback():
    for form in ("8-K", "8-K/A", "6-K"):
        title = build_title(
            form_type=form, items=None, primary_doc_description="😀" * 200, first_line=None
        )
        assert len(title) == 120 and title[5:] == "😀" * 115
    assert (
        build_title(
            form_type="6-K",
            items=None,
            primary_doc_description="Fallback",
            first_line="\n\n e\u0301 first\nsecond",
        )
        == "6-K: é first"
    )
