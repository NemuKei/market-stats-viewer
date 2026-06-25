from pathlib import Path

from scripts.build_external_events_manifest import _build_manifest


def test_manifest_includes_lp_events_asset(tmp_path: Path):
    for filename in ("events.sqlite", "event_signals.sqlite", "lp_events.json"):
        (tmp_path / filename).write_bytes(f"{filename}\n".encode("utf-8"))

    manifest = _build_manifest(tmp_path, "external-events-latest")

    assert sorted(manifest["assets"].keys()) == [
        "event_signals.sqlite",
        "events.sqlite",
        "lp_events.json",
    ]
    assert manifest["assets"]["lp_events.json"]["size_bytes"] > 0
