#!/usr/bin/env bash
# Railway executes this file directly; .gitattributes keeps it LF-only on Windows checkouts.
set -e

AUTO_UPDATE="${AUTO_UPDATE:-true}"

if [ "$AUTO_UPDATE" = "true" ]; then
  echo "Checking for Hermes updates..."
  cd /opt/hermes-agent
  if git pull --recurse-submodules 2>&1 | grep -v 'Already up to date'; then
    echo "Updating dependencies..."
    VIRTUAL_ENV=/opt/hermes-agent/venv uv pip install -e ".[all]" --quiet
    echo "Update complete."
  else
    echo "Already up to date."
  fi
fi

# This profile artifact described Workers-owned Discord reply lanes that no longer exist.
# Remove it after upstream sync and before the gateway builds its active skill catalog.
rm -rf -- /root/.hermes/skills/tfas-ops/discord-worker-message-intake

hermes dashboard --host 127.0.0.1 --port 9119 --no-open &

exec python /auth_proxy.py
