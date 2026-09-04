from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github/workflows/publish_external_events_assets.yml"
)


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_publish_workflow_covers_direct_main_asset_pushes():
    workflow = _workflow_text()

    assert "  push:\n    branches:\n      - main\n" in workflow
    for path in (
        ".github/workflows/publish_external_events_assets.yml",
        "data/events.sqlite",
        "data/event_signals.sqlite",
        "data/lp_events.json",
        "scripts/build_external_events_manifest.py",
    ):
        assert f"      - {path}\n" in workflow
    assert "github.event_name == 'push' ||" in workflow


def test_publish_workflow_retains_fallbacks_and_serializes_release_updates():
    workflow = _workflow_text()

    assert "  workflow_dispatch:\n" in workflow
    assert "  workflow_run:\n" in workflow
    assert "group: external-events-latest" in workflow
    assert "cancel-in-progress: false" in workflow
