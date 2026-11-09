import pytest

from scripts import update_ta_data as updater


def test_fiscal_discovery_accepts_current_and_legacy_official_pages():
    html = """
    <a href="/kankocho/page06_00039.html">令和8年度（2026年度）</a>
    <a href="/kankocho/page06_00039.html">令和8年度（2026年度）</a>
    <a href="ryokogyotoriatsukaigaku_r7.html">令和7年度（2025年度）</a>
    <a href="/kankocho/ryokogyotoriatsukaigaku_r4.html">令和4年度（2022年度）</a>
    """
    pages = updater.extract_fiscal_page_links(html, updater.TA_SOURCE_INDEX_URL)
    assert [updater.parse_fiscal_year(p["link_text"]) for p in pages] == [
        "2026",
        "2025",
        "2022",
    ]
    assert pages[0]["url"] == "https://www.mlit.go.jp/kankocho/page06_00039.html"


@pytest.mark.parametrize(
    "url,label",
    [
        ("https://evil.example/kankocho/page06_00039.html", "2026年度"),
        ("https://www.mlit.go.jp.evil.example/kankocho/page06_00039.html", "2026年度"),
        ("https://www.mlit.go.jp@evil.example/kankocho/page06_00039.html", "2026年度"),
        ("https://evil.example/ryokogyotoriatsukaigaku_r8.html", "2026年度"),
        ("/kankocho/page06_00039.html", "関連情報"),
        ("/kankocho/page06_00039.html", "令和8年度"),
        ("/unrelated/page06_00039.html", "2026年度"),
        ("/kankocho/unrelated.html", "2026年度"),
        ("/kankocho/page06_00039.html?redirect=elsewhere", "2026年度"),
        ("/kankocho/other.html?ryokogyotoriatsukaigaku_r8.html", "2026年度"),
        ("/kankocho/page06_00039.html/extra", "2026年度"),
        ("https://www.mlit.go.jp:444/kankocho/page06_00039.html", "2026年度"),
    ],
)
def test_fiscal_discovery_rejects_untrusted_or_unrelated_links(url, label):
    with pytest.raises(RuntimeError, match="No fiscal-year"):
        updater.extract_fiscal_page_links(
            f'<a href="{url}">{label}</a>', updater.TA_SOURCE_INDEX_URL
        )


def test_legacy_page_can_still_use_title_for_year():
    pages = updater.extract_fiscal_page_links(
        '<a href="/kankocho/tokei_hakusyo/ryokogyotoriatsukaigaku_r7.html">資料</a>',
        updater.TA_SOURCE_INDEX_URL,
    )
    assert len(pages) == 1


@pytest.mark.parametrize("inherit_cell_strike", [False, True])
def test_rich_text_replacement_overrides_cancelled_cell_font(
    tmp_path, inherit_cell_strike
):
    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Font

    book = Workbook()
    sheet = book.active
    sheet["C4"] = "合計"
    sheet["C5"] = "2026年"
    sheet["C6"] = "取扱額（千円）"
    sheet["B7"] = "ANA X(株)"
    replacement = "5,725,720\n"
    sheet["C7"] = CellRichText(
        [
            replacement
            if inherit_cell_strike
            else TextBlock(InlineFont(rFont="ＭＳ Ｐゴシック"), replacement),
            TextBlock(InlineFont(strike=True), "5,465,081"),
        ]
    )
    sheet["C7"].font = Font(strike=True)
    source = tmp_path / "correction.xlsx"
    book.save(source)
    book.close()
    if inherit_cell_strike:
        with pytest.raises(ValueError, match="cancelled"):
            updater.parse_ta_excel_rows(source, "2026", "2026-08")
    else:
        assert (
            updater.parse_ta_excel_rows(source, "2026", "2026-08")[0]["amount"]
            == 5725720.0
        )


@pytest.mark.parametrize(
    "case",
    [
        "explicit_false",
        "all_cancelled",
        "multiple_values",
        "mixed_inherited",
        "plain_cancelled",
    ],
)
def test_cancelled_cell_rich_text_safety(tmp_path, case):
    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Font

    values = {
        "explicit_false": CellRichText(
            [
                TextBlock(InlineFont(strike=False), "123"),
                TextBlock(InlineFont(strike=True), "456"),
            ]
        ),
        "all_cancelled": CellRichText([TextBlock(InlineFont(strike=True), "123")]),
        "multiple_values": CellRichText(
            [
                TextBlock(InlineFont(strike=False), "123\n"),
                TextBlock(InlineFont(strike=False), "456"),
            ]
        ),
        "mixed_inherited": CellRichText(
            [TextBlock(InlineFont(strike=False), "123"), "456"]
        ),
        "plain_cancelled": 123,
    }
    book = Workbook()
    sheet = book.active
    sheet["C4"], sheet["C5"], sheet["C6"], sheet["B7"] = (
        "合計",
        "2026年",
        "取扱額（千円）",
        "会社A",
    )
    sheet["C7"] = values[case]
    sheet["C7"].font = Font(strike=True)
    source = tmp_path / "safety.xlsx"
    book.save(source)
    book.close()
    if case == "explicit_false":
        assert (
            updater.parse_ta_excel_rows(source, "2026", "2026-08")[0]["amount"] == 123
        )
    else:
        with pytest.raises(ValueError):
            updater.parse_ta_excel_rows(source, "2026", "2026-08")
