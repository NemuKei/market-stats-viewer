from pathlib import Path


WORKFLOW_PATH = Path(__file__).parents[1] / ".github/workflows/publish_external_events_assets.yml"


def test_publish_external_events_assets_runs_for_direct_main_asset_pushes():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert """  push:
    branches:
      - main
    paths:
      - data/events.sqlite
      - data/event_signals.sqlite
      - data/lp_events.json
      - scripts/build_external_events_manifest.py
      - .github/workflows/publish_external_events_assets.yml
""" in workflow
    assert "github.event_name == 'push'" in workflow
    assert "group: external-events-release" in workflow
