from scripts.venue_web_discovery_extract import _crawl4ai_links, _crawl4ai_markdown_text, compact_text


def test_compact_text_normalizes_whitespace():
    assert compact_text("  a\n\n b\t c  ") == "a b c"


def test_crawl4ai_markdown_text_accepts_object_shapes():
    markdown = type("Markdown", (), {"fit_markdown": "  fit\nmarkdown  ", "raw_markdown": "raw"})()
    result = type("Result", (), {"markdown": markdown})()

    assert _crawl4ai_markdown_text(result) == "fit markdown"


def test_crawl4ai_links_accepts_grouped_links():
    result = type(
        "Result",
        (),
        {
            "links": {
                "internal": [{"href": "https://example.com/a"}, {"href": "https://example.com/a"}],
                "external": ["https://example.org/b"],
            }
        },
    )()

    assert _crawl4ai_links(result) == ["https://example.com/a", "https://example.org/b"]


def test_declared_html_charset_overrides_requests_latin1_default():
    from requests import Response
    from scripts.venue_web_discovery_extract import extract_with_requests_bs4
    response = Response()
    response.status_code = 200
    response.encoding = 'ISO-8859-1'
    response._content = '<meta charset="utf-8"><p>大阪公演 ペルソナ 2026年9月13日</p>'.encode()
    session = type('Session', (), {'get': lambda self, *a, **kw: response})()
    result = extract_with_requests_bs4('https://example.com', session=session)
    assert '大阪公演 ペルソナ' in result.text
