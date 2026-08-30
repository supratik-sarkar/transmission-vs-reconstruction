from handoff_fidelity.source_pool import extract_item7, html_to_text


def test_item7_extraction() -> None:
    html = """
    <html><body>
    <h2>Item 7. Management's Discussion and Analysis</h2>
    <p>Revenue increased 6.2%.</p>
    <h2>Item 7A. Quantitative and Qualitative Disclosures</h2>
    <p>Risk text.</p>
    </body></html>
    """
    text = html_to_text(html)
    out = extract_item7(text)
    assert "Revenue increased 6.2%" in out
    assert "Risk text" not in out
