from pathlib import Path
import unittest


WORKFLOW_PATH = Path(".github/workflows/publish_external_events_assets.yml")


class PublishExternalEventsWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    def test_direct_main_pushes_trigger_publication(self) -> None:
        push_block = self.workflow.split("  push:\n", 1)[1].split(
            "  workflow_dispatch:\n", 1
        )[0]
        self.assertIn("    branches:\n      - main\n", push_block)
        for path in (
            ".github/workflows/publish_external_events_assets.yml",
            "data/events.sqlite",
            "data/event_signals.sqlite",
            "data/lp_events.json",
        ):
            self.assertIn(f"      - {path}\n", push_block)
        self.assertIn("github.event_name == 'push'", self.workflow)

    def test_existing_automatic_and_manual_routes_remain(self) -> None:
        self.assertIn("  workflow_dispatch:\n", self.workflow)
        self.assertIn("  workflow_run:\n", self.workflow)
        for workflow_name in (
            "Update events official data",
            "Update event signals data (News)",
            "Update event signals data (Ticketjam)",
            "Update event signals data (Venue Web Discovery)",
        ):
            self.assertIn(f"      - {workflow_name}\n", self.workflow)
        self.assertIn(
            "github.event.workflow_run.conclusion == 'success'", self.workflow
        )
        self.assertIn(
            "github.event.workflow_run.head_branch == 'main'", self.workflow
        )


if __name__ == "__main__":
    unittest.main()
