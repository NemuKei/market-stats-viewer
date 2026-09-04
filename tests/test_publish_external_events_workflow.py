from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/publish_external_events_assets.yml")
DIRECT_PUSH_PATHS = (
    ".github/workflows/publish_external_events_assets.yml",
    "data/events.sqlite",
    "data/event_signals.sqlite",
    "data/lp_events.json",
    "scripts/build_external_events_manifest.py",
)


def test_publish_workflow_covers_direct_main_pushes() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "  push:\n" in workflow
    assert "    branches:\n      - main\n" in workflow
    assert "    paths:\n" in workflow
    for path in DIRECT_PUSH_PATHS:
        assert f"      - {path}\n" in workflow

    assert "github.event_name == 'push'" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "github.event_name == 'workflow_run'" in workflow
    assert "github.event_name == 'push' && github.sha || 'main'" in workflow
