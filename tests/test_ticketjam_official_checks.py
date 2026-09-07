from scripts.ticketjam_official_checks import verify_npb, verify_zepp


def candidate(**kwargs):
    return {
        "event_key": "lead",
        "event_date": "2026-09-08",
        "event_start_time": "18:00",
        "venue_name": "東京ドーム",
        "artist_name": "読売ジャイアンツ",
        "title": "巨人 vs 中日",
        **kwargs,
    }


def test_npb_date_venue_opponents_and_start_must_all_match():
    html = "<h1>2026年9月 試合日程</h1><p>9/8（火） 巨人 - 中日 東京ドーム 18:00</p><p>9/9（水） 巨人 - 中日 東京ドーム 19:00</p>"
    url = "https://npb.jp/games/2026/schedule_09_detail.html"
    assert verify_npb(candidate(), html, url)
    assert verify_npb(candidate(event_start_time="19:00"), html, url) is None
    assert verify_npb(candidate(venue_name="阪神甲子園球場"), html, url) is None
    assert verify_npb(candidate(title="巨人 vs 中日 駐車券"), html, url) is None


def test_zepp_matches_each_start_and_never_uses_open_time():
    c = candidate(
        venue_name="Zepp Haneda(Tokyo)",
        artist_name="Example Artist",
        title="Example Artist Tour 2026",
    )
    html = '<a href="single/?rid=1"><span>2026 9.8 TUE</span><h3>Example Artist</h3><h4>Example Artist Tour 2026</h4>[OPEN] 13:00 [START] 14:00 [OPEN] 17:00 [START] 18:00</a>'
    url = "https://www.zepp.co.jp/hall/haneda/schedule/?_y=2026&_m=9"
    assert verify_zepp(c, html, url)
    assert verify_zepp({**c, "event_start_time": "14:00"}, html, url)
    assert verify_zepp({**c, "event_start_time": "17:00"}, html, url) is None
    assert verify_zepp({**c, "event_date": "2026-09-09"}, html, url) is None


def test_cancelled_zepp_performance_is_not_claimed_as_scheduled():
    c = candidate(
        venue_name="Zepp Haneda(Tokyo)",
        artist_name="Example Artist",
        title="Example Artist Tour 2026",
    )
    html = '<a href="single/?rid=1"><span>2026 9.8 TUE</span><h3>【公演中止】Example Artist Tour 2026</h3>[START] 18:00</a>'
    assert (
        verify_zepp(c, html, "https://www.zepp.co.jp/hall/haneda/schedule/")[
            "event_status"
        ]
        == "cancelled"
    )


def test_matching_title_does_not_authorize_an_unrelated_artist():
    c = candidate(
        venue_name="Zepp Haneda(Tokyo)",
        artist_name="Unrelated Band",
        title="Example Artist Tour 2026",
    )
    html = '<a href="single/?rid=1"><span>2026 9.8 TUE</span><h3>Example Artist</h3><h4>Example Artist Tour 2026</h4>[START] 18:00</a>'
    assert verify_zepp(c, html, "https://www.zepp.co.jp/hall/haneda/schedule/") is None


def test_zepp_performer_h2_is_used_for_short_artist_name():
    c = candidate(
        venue_name="Zepp Fukuoka", artist_name="陰陽座", title="陰陽座ツアー2026 流転"
    )
    html = '<a href="single/?rid=1"><span>2026 9.8 TUE</span><h2>陰陽座</h2><h3>陰陽座ツアー2026 流転</h3>[START] 18:00</a>'
    assert verify_zepp(c, html, "https://www.zepp.co.jp/hall/fukuoka/schedule/")


def test_npb_does_not_copy_an_unrelated_artist_from_secondary_data():
    html = "<h1>2026年9月</h1><p>9/8（火） 巨人 - 中日 東京ドーム 18:00</p>"
    assert (
        verify_npb(
            candidate(artist_name="Unrelated Band"),
            html,
            "https://npb.jp/games/2026/schedule_09_detail.html",
        )
        is None
    )


def test_npb_year_in_footer_does_not_validate_an_old_schedule():
    html = "<h4>2025年</h4><p>9/8（火） 巨人 - 中日 東京ドーム 18:00</p><footer>2026</footer>"
    assert (
        verify_npb(
            candidate(), html, "https://npb.jp/games/2026/schedule_09_detail.html"
        )
        is None
    )
