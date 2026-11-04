from sentinel.markets.sec.extract import html_to_text


def test_html_to_text_removes_scripts_and_keeps_table():
    html = """<head><style>CSS</style></head><script>alert(1)</script><!--secret-->
    <table><tr><td>A</td><td>B</td></tr><tr><td>C</td><td>D</td></tr></table>"""
    text = html_to_text(html)
    assert "A | B" in text and "C | D" in text
    assert all(word not in text for word in ("alert", "CSS", "secret"))
    assert html_to_text("") == ""


def test_html_to_text_xbrl_and_truncation():
    text = html_to_text("<p><ix:nonfraction>42</ix:nonfraction></p>")
    assert "42" in text and "ix:" not in text
    assert len(html_to_text("<p>" + "a" * 250000 + "</p>")) == 200000


def test_utf_codepoints_nfc_controls_and_spacing():
    text = html_to_text("<p>e\u0301&nbsp;😀\x00\x01\x7f</p><div>A\t  B<br>C</div>")
    assert text == "é 😀\n\nA B\n\nC"
    assert len(html_to_text("<p>" + "😀" * 200001 + "</p>")) == 200000
    assert html_to_text("<script>hidden</script><noscript>hidden</noscript><!--hidden-->") == ""


def test_nested_table_and_inline_markup_text_survives():
    text = html_to_text(
        "<table><tr><th>Metric</th><th>Value</th></tr>"
        "<tr><td><b>Sales</b></td><td><ix:nonfraction>42</ix:nonfraction></td>"
        "</tr></table><a href='https://evil.example'>Visible link</a>"
    )
    assert "Metric | Value" in text and "Sales | 42" in text
    assert "Visible link" in text and "evil.example" not in text
