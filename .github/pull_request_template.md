## Outcome

<!-- What operator or runtime outcome changes? -->

## Verification

- [ ] `bash -n entrypoint.sh`
- [ ] `python -m py_compile auth_proxy.py`
- [ ] `python -m json.tool railway.json`
- [ ] Docker image built locally or `Validate / validate` passed
- [ ] No passwords, provider keys, OAuth files, bot tokens, SSH keys, or volume data included

## Production impact

- [ ] No release needed (docs/tests only)
- [ ] Hermes container release required
- [ ] Railway variable/dashboard change required

If a release is required:

- [ ] Release owner named
- [ ] SiteForge active runs were empty
- [ ] No other Railway deployment was in progress
- [ ] Persistent `/root/.hermes` volume remains attached
- [ ] Separate `ops/railway-release/` marker PR planned

## Rollback

<!-- Name the last-known-good deployment or exact revert. -->
