#!/usr/bin/env bash
# Railway executes this file directly; .gitattributes keeps it LF-only on Windows checkouts.
set -e

AUTO_UPDATE="${AUTO_UPDATE:-true}"

if [ "$AUTO_UPDATE" = "true" ]; then
  echo "Checking for Hermes updates..."
  cd /opt/hermes-agent
  # runtime_policy.py patches this exact upstream file after update. Restore only that
  # container-owned patch before pulling so a later upstream update is never blocked.
  git restore -- tools/discord_tool.py
  if git pull --recurse-submodules 2>&1 | grep -v 'Already up to date'; then
    echo "Updating dependencies..."
    VIRTUAL_ENV=/opt/hermes-agent/venv uv pip install -e ".[all]" --quiet
    echo "Update complete."
  else
    echo "Already up to date."
  fi
fi

# Reconcile TFAS routing after upstream sync and before the gateway builds its tool/skill catalog.
# This keeps native mention-to-thread behavior, but prevents an agent turn from opening an
# unanchored shadow thread in another channel.
python /runtime_policy.py

hermes dashboard --host 127.0.0.1 --port 9119 --no-open &

exec python /auth_proxy.py
