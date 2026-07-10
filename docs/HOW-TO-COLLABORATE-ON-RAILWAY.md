# How to collaborate and release Hermes on Railway

This guide lets multiple contributors update the TFAS Hermes container without losing persistent
memory/auth, duplicating the Discord gateway, or redeploying every time documentation changes.

## Service model

```text
GitHub TipForASite/hermes-agent-railway (main)
          |
          | Railway watches ops/railway-release/** only
          v
Railway project tfas / service hermes / production
          |
          +-- container code: Dockerfile + entrypoint.sh + auth_proxy.py
          +-- persistent state: /root/.hermes (50GB Railway volume)
          +-- public health: /api/health
          +-- Discord gateway: one process, one TFAS Hermes bot
          +-- private SSH: tfas-workers.railway.internal:2222
```

`Dockerfile` clones upstream Hermes into the image. At boot, `entrypoint.sh` pulls upstream again
when `AUTO_UPDATE=true`, starts the dashboard, and runs the authentication proxy. TFAS config,
skills, cron jobs, sessions, and OAuth state live on the volume, not in this repository.

## Prerequisites

- Contributor access to `TipForASite/hermes-agent-railway`.
- Railway project access for release operators.
- GitHub CLI and Railway CLI 5.26 or newer.
- Docker for a full local image build. Contributors without Docker can rely on GitHub CI.

```powershell
gh auth status
railway whoami
```

## Make a change

1. Branch from remote `main`:

   ```powershell
   git fetch origin
   git switch -c codex/<short-task> origin/main
   git status --short
   ```

2. Validate the static files:

   ```powershell
   bash -n entrypoint.sh
   python -m py_compile auth_proxy.py
   python -m json.tool railway.json > $null
   git diff --check
   ```

3. For runtime changes, build the image:

   ```powershell
   docker build --tag tfas-hermes-local .
   ```

4. Stage only your files, push, and open a PR:

   ```powershell
   git add -- <file-1> <file-2>
   git commit -m "<type>: <outcome>"
   git push -u origin HEAD
   gh pr create --fill
   ```

5. Merge after `Validate / validate` passes. A normal merge does not deploy because Railway watches
   only release markers.

## Release to Railway

1. Announce one release owner. Check both services and the SiteForge run queue:

   ```powershell
   railway deployment list --service hermes --limit 3
   railway deployment list --service tfas-workers --limit 3
   ```

   Ask Hermes in `#tfas-operational` to list active SiteForge runs, or run `npm run ops:cli -- runs`
   from an authorized SiteForge checkout. Continue only when `active` is empty.

2. Create a marker PR from the tested `main` commit:

   ```powershell
   git fetch origin
   $stamp = Get-Date -Format yyyyMMdd-HHmm
   git switch -c "release/hermes-$stamp" origin/main
   New-Item -ItemType Directory -Force ops/railway-release | Out-Null
   $sha = git rev-parse origin/main
   $short = $sha.Substring(0, 8)
   $marker = "ops/railway-release/$stamp-$short.md"
   Set-Content -LiteralPath $marker "Release $sha after empty-runs gate."
   git add -- $marker
   git commit -m "ops: release Hermes $short"
   git push -u origin HEAD
   gh pr create --fill
   ```

3. Merge the marker after CI passes. Poll Railway:

   ```powershell
   railway deployment list --service hermes --limit 3
   railway logs --service hermes --lines 200
   railway service status --service hermes
   ```

4. Verify the public service:

   ```powershell
   Invoke-WebRequest -UseBasicParsing https://hermes-production-d0c6.up.railway.app/api/health
   ```

5. Verify stateful behavior from an authorized operator session:

   ```text
   hermes status
   hermes cron list
   ```

   Required evidence: OpenAI Codex logged in, Discord configured, gateway running, two active TFAS
   cron jobs, and private worker SSH reachable. Run a real `hermes chat` probe after provider/auth
   changes.

## Secrets and persistent state

- Store secrets in Railway variables or the Hermes dashboard. Never place values in GitHub Actions.
- Do not use `railway variable list --json` in logs; it returns raw values.
- Batch variable changes with `--skip-deploys`, then use one controlled marker release if a restart
  is needed.
- Never copy the worker `/data/home/.codex/auth.json` into Hermes. Each runtime owns its refresh
  token.
- Do not delete, replace, or re-mount `/root/.hermes` during a release.

## Roll back

If health fails, Railway should retain the last healthy deployment.

1. Capture the failed deployment id and logs.
2. In Railway, open `hermes` → Deployments and redeploy the last successful deployment.
3. Revert the bad GitHub commit through a PR.
4. Verify `/api/health`, gateway status, provider auth, cron jobs, and worker SSH again.

Do not create a new Hermes service as a shortcut. A second service can connect a duplicate Discord
gateway and will not share the verified volume automatically.

## Troubleshooting

### A merged change did not deploy

Expected. Merge a reviewed `ops/railway-release/` marker after the drain gate.

### Health is green but Discord does not answer

`/api/health` covers the proxy, not the gateway session. Run `hermes status`, inspect Railway logs,
and use the authenticated gateway restart endpoint or dashboard widget once. Do not start a second
gateway process manually.

### Auth disappeared after redeploy

Confirm the service still mounts the 50GB volume at `/root/.hermes`. If the mount is present, inspect
`hermes auth list` without printing tokens. Re-authenticate Hermes itself; do not copy worker OAuth.

### The container unexpectedly changed Hermes versions

`AUTO_UPDATE=true` pulls upstream during boot. Set `AUTO_UPDATE=false` in Railway if a pinned incident
window is required, then release once and document the pin. Re-enable only after testing upstream.
