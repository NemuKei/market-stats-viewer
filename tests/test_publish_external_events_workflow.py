from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github/workflows/publish_external_events_assets.yml"


def test_publish_workflow_covers_direct_main_pushes() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    expected_push_trigger = """  push:
    branches:
      - main
    paths:
      - data/events.sqlite
      - data/event_signals.sqlite
      - data/lp_events.json
      - scripts/build_external_events_manifest.py
      - .github/workflows/publish_external_events_assets.yml
"""

    assert expected_push_trigger in workflow
    assert "github.event_name == 'push' ||" in workflow
