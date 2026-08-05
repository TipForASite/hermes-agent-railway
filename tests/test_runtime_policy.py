import json
import tempfile
from pathlib import Path
import unittest

import runtime_policy


DISCORD_TOOL_FIXTURE = '''import json

def _create_thread(
    token: str, channel_id: str, name: str,
    message_id=None,
) -> str:
    """Create a thread in a channel."""
    if message_id:
        path = f"/channels/{channel_id}/messages/{message_id}/threads"
    else:
        path = f"/channels/{channel_id}/threads"
    return json.dumps({"path": path})

_ACTION_MANIFEST = [
    ("create_thread", "(channel_id, name)", "create a public thread; optional message_id anchor"),
]
'''

CONFIG_FIXTURE = '''discord:
  require_mention: true
  channel_prompts:
    '1524901024203276550': TFAS OPERATIONS MODE. Old factory prompt that allowed ambiguity.
    '1524901024853135501': TFAS INTERNAL MODE. Move engineering work to system-dev.
command_allowlist:
  - execute_code
'''


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.hermes_root = self.root / "opt-hermes"
        self.hermes_home = self.root / "home-hermes"
        (self.hermes_root / "tools").mkdir(parents=True)
        (self.hermes_home / runtime_policy.OBSOLETE_SKILL).mkdir(parents=True)
        (self.hermes_root / "tools/discord_tool.py").write_text(
            DISCORD_TOOL_FIXTURE, encoding="utf-8"
        )
        (self.hermes_home / "config.yaml").write_text(CONFIG_FIXTURE, encoding="utf-8")
        (self.hermes_home / runtime_policy.OBSOLETE_SKILL / "SKILL.md").write_text(
            "retired", encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_reconcile_enforces_single_anchored_thread_policy(self):
        result = runtime_policy.reconcile(self.hermes_root, self.hermes_home)

        self.assertEqual(
            result,
            {
                "discord_tool_patched": True,
                "channel_prompts_patched": True,
                "obsolete_worker_intake_removed": True,
            },
        )
        discord_tool = (self.hermes_root / "tools/discord_tool.py").read_text()
        self.assertIn(runtime_policy.THREAD_POLICY_MARKER, discord_tool)
        self.assertIn('if not message_id:', discord_tool)
        self.assertIn('"unanchored_thread_creation_disabled"', discord_tool)
        self.assertIn("message_id is required", discord_tool)
        namespace = {}
        exec(compile(discord_tool, "discord_tool.py", "exec"), namespace)
        rejected = json.loads(namespace["_create_thread"]("token", "channel", "name"))
        self.assertEqual(rejected["error"], "unanchored_thread_creation_disabled")
        anchored = json.loads(
            namespace["_create_thread"]("token", "channel", "name", message_id="message")
        )
        self.assertEqual(anchored["path"], "/channels/channel/messages/message/threads")

        config = (self.hermes_home / "config.yaml").read_text()
        self.assertIn("directly addressed conversation is the canonical work thread", config)
        self.assertIn("never create a parallel System Dev", config)
        self.assertIn("create exactly one thread anchored to an existing message", config)
        self.assertIn("command_allowlist:", config)
        self.assertFalse((self.hermes_home / runtime_policy.OBSOLETE_SKILL).exists())

    def test_reconcile_is_idempotent(self):
        runtime_policy.reconcile(self.hermes_root, self.hermes_home)
        second = runtime_policy.reconcile(self.hermes_root, self.hermes_home)
        self.assertEqual(
            second,
            {
                "discord_tool_patched": False,
                "channel_prompts_patched": False,
                "obsolete_worker_intake_removed": False,
            },
        )

    def test_discord_tool_drift_fails_closed(self):
        path = self.hermes_root / "tools/discord_tool.py"
        path.write_text("def _create_thread():\n    pass\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "policy anchor missing"):
            runtime_policy.patch_discord_tool(path)

    def test_current_fixture_passes_non_mutating_compatibility_check(self):
        path = self.hermes_root / "tools/discord_tool.py"
        before = path.read_text(encoding="utf-8")
        runtime_policy.check_discord_tool_compatibility(path)
        self.assertEqual(path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
