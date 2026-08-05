#!/usr/bin/env python3
"""Apply TFAS-specific Hermes routing policy before the gateway starts."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


THREAD_POLICY_MARKER = "# TFAS_CANONICAL_THREAD_POLICY"
OBSOLETE_SKILL = Path("skills/tfas-ops/discord-worker-message-intake")

FACTORY_CHANNEL_ID = "1524901024203276550"
INTERNAL_CHANNEL_ID = "1524901024853135501"

FACTORY_PROMPT = (
    "TFAS OPERATIONS MODE. Act as the operations manager. Use the tfas-ops skills and "
    "ops-cli only for client or fleet mutations, always with actor attribution. The directly "
    "addressed conversation is the canonical work thread. If the work requires an engineering "
    "change, perform and narrate it from that origin thread; never create a parallel System Dev "
    "or engineering thread. If the operator explicitly asks for a client thread, create exactly "
    "one fresh standalone thread in that client's channel, then keep relevant progress there. "
    "Never attach it to, reuse, or rename an older Workers message or thread. Do not also create "
    "or rename another thread. Give concise actionable status, "
    "escalate money or legality ambiguity, and never type the human gate words in build channels."
)

INTERNAL_PROMPT = (
    "TFAS INTERNAL MODE. Answer operational questions using the tfas-ops skills. Use ops-cli for "
    "any mutation and recall client memory before judgment calls. The directly addressed "
    "conversation is the canonical work thread. Keep any resulting engineering work in that "
    "origin thread; never create a parallel System Dev or engineering thread. If the operator "
    "explicitly asks for a client thread, create exactly one fresh standalone thread in that "
    "client's channel. Never attach it to, reuse, or rename an older Workers message or thread, "
    "and do not create or rename any other thread."
)

_CREATE_THREAD_NEEDLE = '''    """Create a thread in a channel."""
    if message_id:
'''

_CREATE_THREAD_REPLACEMENT = '''    """Create a thread in a channel."""
    # TFAS_CANONICAL_THREAD_POLICY
    # Native mention-to-thread routing owns internal rooms. The agent may create a standalone
    # cross-channel thread only in a real TFAS client channel; this keeps the thread Hermes-owned
    # instead of attaching it to an old Workers card, while blocking shadow engineering threads.
    if not message_id:
        target = _discord_request("GET", f"/channels/{channel_id}", token)
        target_name = str(target.get("name") or "").lower()
        target_topic = str(target.get("topic") or "").lower()
        is_tfas_client_channel = (
            target.get("type") == 0
            and target_name.startswith("tfas-")
            and "lead " in target_topic
        )
        if not is_tfas_client_channel:
            return json.dumps({
                "success": False,
                "error": "standalone_thread_limited_to_client_channels",
                "hint": (
                    "Keep engineering work in the current origin thread. Standalone tool-created "
                    "threads are allowed only in a TFAS client channel."
                ),
            })
    if message_id:
'''

_MANIFEST_OLD = (
    '("create_thread", "(channel_id, name)", '
    '"create a public thread; optional message_id anchor"),'
)
_MANIFEST_NEW = (
    '("create_thread", "(channel_id, name[, message_id])", '
    '"create one thread; omit message_id only for a fresh standalone TFAS client thread"),'
)


def _atomic_write(path: Path, content: str) -> None:
    """Replace a text file without exposing a partially written policy."""

    mode = path.stat().st_mode
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.chmod(temporary, mode)
    temporary.replace(path)


def patch_discord_tool(path: Path) -> bool:
    """Limit standalone agent-created threads to genuine TFAS client channels."""

    content = path.read_text(encoding="utf-8")
    changed = False

    if THREAD_POLICY_MARKER not in content:
        check_discord_tool_compatibility(path, content=content)
        content = content.replace(_CREATE_THREAD_NEEDLE, _CREATE_THREAD_REPLACEMENT, 1)
        changed = True

    if _MANIFEST_OLD in content:
        content = content.replace(_MANIFEST_OLD, _MANIFEST_NEW, 1)
        changed = True
    elif _MANIFEST_NEW not in content:
        raise RuntimeError(
            f"Hermes Discord action manifest changed; policy description missing in {path}"
        )

    if changed:
        _atomic_write(path, content)
    return changed


def check_discord_tool_compatibility(path: Path, *, content: str | None = None) -> None:
    """Fail a build/release when upstream no longer exposes the guarded patch anchors."""

    source = content if content is not None else path.read_text(encoding="utf-8")
    if THREAD_POLICY_MARKER in source:
        if _MANIFEST_NEW not in source:
            raise RuntimeError(
                f"Patched Hermes Discord action manifest is missing from {path}"
            )
        return
    if _CREATE_THREAD_NEEDLE not in source:
        raise RuntimeError(
            f"Hermes Discord thread implementation changed; policy anchor missing in {path}"
        )
    if _MANIFEST_OLD not in source:
        raise RuntimeError(
            f"Hermes Discord action manifest changed; policy description missing in {path}"
        )


def _replace_channel_prompt(content: str, channel_id: str, prompt: str) -> tuple[str, bool]:
    pattern = re.compile(
        rf"^    '{re.escape(channel_id)}':.*?"
        rf"(?=^    '[0-9]+':|^[A-Za-z_][A-Za-z0-9_-]*:|\Z)",
        flags=re.MULTILINE | re.DOTALL,
    )
    replacement = f"    '{channel_id}': {json.dumps(prompt)}\n"
    updated, count = pattern.subn(replacement, content, count=1)
    return updated, bool(count) and updated != content


def patch_channel_prompts(path: Path) -> bool:
    """Make the addressed Factory/Internal thread the only engineering conversation."""

    content = path.read_text(encoding="utf-8")
    updated, factory_changed = _replace_channel_prompt(
        content, FACTORY_CHANNEL_ID, FACTORY_PROMPT
    )
    if FACTORY_CHANNEL_ID not in updated:
        raise RuntimeError(f"Factory channel prompt is missing from {path}")

    updated, internal_changed = _replace_channel_prompt(
        updated, INTERNAL_CHANNEL_ID, INTERNAL_PROMPT
    )
    if INTERNAL_CHANNEL_ID not in updated:
        raise RuntimeError(f"Internal channel prompt is missing from {path}")

    changed = factory_changed or internal_changed
    if changed:
        _atomic_write(path, updated)
    return changed


def remove_obsolete_worker_intake(hermes_home: Path) -> bool:
    """Remove the retired conversational Workers lane from the active skill catalog."""

    target = hermes_home / OBSOLETE_SKILL
    if not target.exists():
        return False
    if not target.is_dir():
        raise RuntimeError(f"Refusing to remove unexpected non-directory path: {target}")
    shutil.rmtree(target)
    return True


def reconcile(hermes_root: Path, hermes_home: Path) -> dict[str, bool]:
    return {
        "discord_tool_patched": patch_discord_tool(hermes_root / "tools/discord_tool.py"),
        "channel_prompts_patched": patch_channel_prompts(hermes_home / "config.yaml"),
        "obsolete_worker_intake_removed": remove_obsolete_worker_intake(hermes_home),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-root", type=Path, default=Path("/opt/hermes-agent"))
    parser.add_argument("--hermes-home", type=Path, default=Path("/root/.hermes"))
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the current upstream Discord patch anchors without changing files.",
    )
    args = parser.parse_args()

    if args.check:
        check_discord_tool_compatibility(args.hermes_root / "tools/discord_tool.py")
        print(json.dumps({"ok": True, "discord_tool_compatible": True}, sort_keys=True))
        return

    result = reconcile(args.hermes_root, args.hermes_home)
    print(json.dumps({"ok": True, **result}, sort_keys=True))


if __name__ == "__main__":
    main()
