import json
import tempfile
from pathlib import Path
import unittest

import runtime_policy


DISCORD_TOOL_FIXTURE = '''import json

def _discord_request(method, path, token):
    if path.endswith("/client-channel"):
        return {"type": 0, "name": "tfas-acme", "topic": "TFAS client — lead 11111111-1111-1111-1111-111111111111"}
    return {"type": 0, "name": "system-dev", "topic": "Factory engineering"}

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

GATEWAY_FIXTURE = '''class GatewayRunner:
    def _schedule_resume_pending_sessions(self, platform=None):
        candidates = [
            entry for entry in self.session_store._entries.values()
                    if entry.resume_pending
                    and not entry.suspended
                    and entry.origin is not None
                    and entry.resume_reason in self._AUTO_RESUME_REASONS
                    and (platform is None or entry.origin.platform == platform)
        ]
'''


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.hermes_root = self.root / "opt-hermes"
        self.hermes_home = self.root / "home-hermes"
        (self.hermes_root / "tools").mkdir(parents=True)
        (self.hermes_root / "gateway").mkdir(parents=True)
        (self.hermes_home / runtime_policy.OBSOLETE_SKILL).mkdir(parents=True)
        (self.hermes_root / "tools/discord_tool.py").write_text(
            DISCORD_TOOL_FIXTURE, encoding="utf-8"
        )
        (self.hermes_root / "gateway/run.py").write_text(
            GATEWAY_FIXTURE, encoding="utf-8"
        )
        (self.hermes_home / "config.yaml").write_text(CONFIG_FIXTURE, encoding="utf-8")
        (self.hermes_home / runtime_policy.OBSOLETE_SKILL / "SKILL.md").write_text(
            "retired", encoding="utf-8"
        )

    def tearDown(self):
        self.tempdir.cleanup()

    def test_reconcile_enforces_single_client_thread_policy(self):
        result = runtime_policy.reconcile(self.hermes_root, self.hermes_home)

        self.assertEqual(
            result,
            {
                "discord_tool_patched": True,
                "gateway_resume_patched": True,
                "channel_prompts_patched": True,
                "obsolete_worker_intake_removed": True,
            },
        )
        discord_tool = (self.hermes_root / "tools/discord_tool.py").read_text()
        self.assertIn(runtime_policy.THREAD_POLICY_MARKER, discord_tool)
        self.assertIn('if not message_id:', discord_tool)
        self.assertIn('"standalone_thread_limited_to_client_channels"', discord_tool)
        self.assertIn("omit message_id only for a fresh standalone TFAS client thread", discord_tool)
        namespace = {}
        exec(compile(discord_tool, "discord_tool.py", "exec"), namespace)
        rejected = json.loads(namespace["_create_thread"]("token", "system-dev", "name"))
        self.assertEqual(rejected["error"], "standalone_thread_limited_to_client_channels")
        standalone = json.loads(namespace["_create_thread"]("token", "client-channel", "name"))
        self.assertEqual(standalone["path"], "/channels/client-channel/threads")
        anchored = json.loads(
            namespace["_create_thread"]("token", "channel", "name", message_id="message")
        )
        self.assertEqual(anchored["path"], "/channels/channel/messages/message/threads")

        gateway = (self.hermes_root / "gateway/run.py").read_text()
        self.assertIn(runtime_policy.PARENT_RESUME_POLICY_MARKER, gateway)
        self.assertIn("entry.origin.platform == Platform.DISCORD", gateway)
        self.assertIn('entry.origin.chat_type in ("group", "channel")', gateway)
        self.assertIn('getattr(entry.origin, "prospective_thread_id", None)', gateway)

        config = (self.hermes_home / "config.yaml").read_text()
        self.assertIn("directly addressed conversation is the canonical work thread", config)
        self.assertIn("never create a parallel System Dev", config)
        self.assertIn("create exactly one fresh standalone thread", config)
        self.assertIn("Never attach it to, reuse, or rename an older Workers message", config)
        self.assertIn("command_allowlist:", config)
        self.assertFalse((self.hermes_home / runtime_policy.OBSOLETE_SKILL).exists())

    def test_reconcile_is_idempotent(self):
        runtime_policy.reconcile(self.hermes_root, self.hermes_home)
        second = runtime_policy.reconcile(self.hermes_root, self.hermes_home)
        self.assertEqual(
            second,
            {
                "discord_tool_patched": False,
                "gateway_resume_patched": False,
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

        gateway_path = self.hermes_root / "gateway/run.py"
        gateway_before = gateway_path.read_text(encoding="utf-8")
        runtime_policy.check_gateway_compatibility(gateway_path)
        self.assertEqual(gateway_path.read_text(encoding="utf-8"), gateway_before)

    def test_gateway_resume_drift_fails_closed(self):
        path = self.hermes_root / "gateway/run.py"
        path.write_text("class GatewayRunner:\n    pass\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "startup-resume implementation changed"):
            runtime_policy.patch_gateway_resume(path)


if __name__ == "__main__":
    unittest.main()
