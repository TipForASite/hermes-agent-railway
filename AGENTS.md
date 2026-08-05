# TFAS Hermes Railway agent operating rules

This repository builds the live TFAS Hermes service. Production runs in Railway project `tfas`,
service `hermes`, environment `production`, with persistent state mounted at `/root/.hermes`.

## Read first

- [Collaborative release guide](docs/HOW-TO-COLLABORATE-ON-RAILWAY.md)
- [SiteForge production runbook](https://github.com/TipForASite/siteforge/blob/main/docs/RAILWAY-RUNTIME.md)
- [Hermes upstream documentation](https://hermes-agent.nousresearch.com/docs)

## Non-negotiable rules

1. Work on a branch and use a pull request. Do not push feature work directly to `main`.
2. Inspect `git status` first and stage only intended files.
3. Never commit dashboard passwords, provider keys, OAuth files, Discord tokens, SSH private keys,
   `/root/.hermes` contents, or Railway variable output.
4. Never replace or clear the `/root/.hermes` volume during a code deployment.
5. Hermes and `tfas-workers` must keep separate OpenAI Codex OAuth refresh sessions.
6. Do not start a second Discord gateway. One bot identity and one gateway own mentions.
7. Do not run `railway up` for ordinary releases. Railway deploys only from reviewed marker files
   under `ops/railway-release/`.
8. Before release, confirm SiteForge has no active builds and no other Railway deployment is active.
9. Never synthesize the client lifecycle words `approved` or `paid`; humans own those gates.
10. Preserve the private SSH route to `tfas-workers.railway.internal:2222` and the public
    `/api/health` endpoint.

## Local validation

```powershell
bash -n entrypoint.sh
python -m py_compile auth_proxy.py runtime_policy.py
python -m unittest discover -s tests -v
python -m json.tool railway.json > $null
docker build --tag tfas-hermes-local .
```

The GitHub `Validate / validate` job repeats these checks in Linux. A release is complete only when
Railway reports `SUCCESS`, `https://hermes-production-d0c6.up.railway.app/api/health` returns 200,
`hermes status` reports the gateway running, and both scheduled TFAS jobs remain active.

## Change classes

| Change | Release behavior |
|---|---|
| Documentation/tests | Merge only; no Railway release marker |
| `auth_proxy.py`, `entrypoint.sh`, `Dockerfile`, `railway.toml`, or `railway.json` | Merge, then controlled release marker |
| Hermes dashboard config or API keys | Change in the dashboard/volume; do not commit |
| Upstream Hermes version behavior | Test in a branch; `AUTO_UPDATE=true` can also update upstream at boot |

Follow [the release guide](docs/HOW-TO-COLLABORATE-ON-RAILWAY.md) for the exact drain, marker,
verification, and rollback sequence.
