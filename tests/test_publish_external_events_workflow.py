from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/publish_external_events_assets.yml")
DIRECT_PUSH_PATHS = (
    ".github/workflows/publish_external_events_assets.yml",
    "data/events.sqlite",
    "data/event_signals.sqlite",
    "data/lp_events.json",
    "scripts/build_external_events_manifest.py",
)


def _workflow_text() -> str:
    return WORKFLOW_PATH.read_text(encoding="utf-8")


def test_publish_workflow_covers_direct_main_pushes() -> None:
    workflow = _workflow_text()

    assert "  push:\n" in workflow
    assert "    branches:\n      - main\n" in workflow
    assert "    paths:\n" in workflow
    for path in DIRECT_PUSH_PATHS:
        assert f"      - {path}\n" in workflow

    assert "github.event_name == 'push'" in workflow
    assert "github.event_name == 'push' && github.sha || 'main'" in workflow


def test_publish_workflow_keeps_safe_existing_entry_points() -> None:
    workflow = _workflow_text()

    assert "  workflow_dispatch:\n" in workflow
    assert "  workflow_run:\n" in workflow
    assert "github.event_name == 'workflow_run'" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "github.event.workflow_run.head_branch == 'main'" in workflow

    for upstream_workflow in (
        "Update events official data",
        "Update event signals data (News)",
        "Update event signals data (Ticketjam)",
        "Update event signals data (Venue Web Discovery)",
    ):
        assert f"      - {upstream_workflow}\n" in workflow


def test_publish_workflow_uploads_complete_external_event_bundle() -> None:
    workflow = _workflow_text()

    expected_upload = (
        "gh release upload external-events-latest "
        "data/events.sqlite data/event_signals.sqlite "
        "data/lp_events.json data/manifest.json --clobber"
    )
    assert expected_upload in workflow
