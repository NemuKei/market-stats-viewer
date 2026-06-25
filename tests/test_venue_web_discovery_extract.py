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
