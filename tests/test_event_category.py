import ast
import json
from pathlib import Path

import pytest

from scripts.events.category import classify_event_category


@pytest.mark.parametrize('title,artist,expected', [
    ('DEEN LIVE JOY-Break27〜ROCK IN CITY〜', '', 'コンサート'),
    ('Mrs. GREEN APPLE ゼンジン未到とイ/ミュータブル〜間奏編〜', 'Mrs. GREEN APPLE', 'コンサート'),
    ('オリックスvs西武', '', '野球'),
    ('都市対抗野球大会', '', '野球'),
    ('明治安田J1百年構想リーグ ガンバ大阪 VS サンフレッチェ広島', '', 'その他'),
    ('2026/27 明治安田J2リーグ 第19節 北海道コンサドーレ札幌vs藤枝MYFC', '北海道コンサドーレ札幌 vs 藤枝MYFC', 'その他'),
    ('りそなグループ B.LEAGUE 2026-27 SEASON B.LEAGUE ONE TUBCホームゲーム 東京ユナイテッドBC vs 立川ダイス', '東京ユナイテッドBC vs 立川ダイス', 'その他'),
    ('学びリンク 通信制高校 合同相談会', '', '未分類'),
    ('展示会', '', 'その他'),
    ("ONE N' ONLY「ドタバタ!? SWAGとひとつ屋根の下で⋯」", '', '未分類'),
    ('RejetFes.2026 Answer', '', '未分類'),
    ('', '', '未分類'),
])
def test_category_regressions(title, artist, expected):
    assert classify_event_category(title, artist, '') == expected


def test_app_uses_shared_classifier():
    tree = ast.parse(Path('app.py').read_text())
    assert not any(isinstance(node, ast.FunctionDef) and node.name == 'classify_event_category' for node in tree.body)
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'scripts.events.category'
               and any(alias.name == 'classify_event_category' for alias in node.names) for node in tree.body)


def test_unknown_has_a_visible_app_filter():
    tree = ast.parse(Path('app.py').read_text())
    options = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == 'EVENT_CATEGORY_OPTIONS' for t in node.targets))
    assert any(isinstance(value, ast.Name) and value.id == 'EVENT_CATEGORY_UNKNOWN' for value in options.elts)


REVIEW_CASES = json.loads(Path('tests/fixtures/category_review_cases.json').read_text())


@pytest.mark.parametrize('case', REVIEW_CASES, ids=lambda case: case['event_uid'])
def test_nine_reviewed_misclassifications(case):
    assert classify_event_category(case['title'], '', '') == case['expected']


@pytest.mark.parametrize('title,expected', [
    ('OSAKA-JO HALL', '未分類'), ('TOKYO DOME', '未分類'), ('ARENA zepp フェス', '未分類'),
    ('LIVE 展示会', '未分類'), ('野球コンサート', '未分類'), ('コンサート 卒業式', '未分類'),
    ('ＦＣ東京×浦和レッズ', 'その他'),
    ('2026なでしこリーグ 第1節 A×B', 'その他'), ('SV.LEAGUE A×B', 'その他'),
    ('大阪交響楽団 定期演奏会', 'コンサート'), ('東京フィルハーモニー', 'コンサート'),
    ('大石昌良×川崎鷹也', '未分類'),
])
def test_conflicts_weak_words_and_new_evidence(title, expected):
    assert classify_event_category(title, '', '') == expected


def test_review_asset_matches_all_nine_regressions():
    asset = json.loads(Path('docs/reviews/schedule-categories-2026-10-29/public_schedule_days.preview.json').read_text())
    by_id = {row['event_uid']: row for row in asset['events']}
    for case in REVIEW_CASES:
        assert by_id[case['event_uid']]['title'] == case['title']
        assert by_id[case['event_uid']]['event_category'] == case['expected']
