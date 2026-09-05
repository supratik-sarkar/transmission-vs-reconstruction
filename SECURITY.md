# Security policy

## Reporting

Please report a suspected vulnerability or an accidental disclosure privately
through the repository's security advisory feature rather than in a public issue.

## What must never enter this repository

- API keys, tokens, service-account files or any other credential
- Raw source documents, snapshots or corpora
- Unpublished run outputs, logs or caches
- Fitted model artifacts and checkpoints
- Freeze material containing local run provenance
- Filesystem paths belonging to a particular machine
- Personal contact details

All of these belong in the private runtime workspace, whose location is supplied
at run time through `HANDOFF_PRIVATE_HOME`.

## Defence in depth

Four independent layers, none of which is a substitute for care:

1. `.gitignore` excludes credential, data, run, cache, artifact and freeze paths.
2. A pre-commit hook runs the privacy scan and a secret scan before a commit
   lands.
3. CI re-runs both and additionally asserts that no runtime artifact directory is
   tracked.
4. `privacy.boundary` refuses to run if the private workspace has become a Git
   repository or has been placed inside this checkout.

## Credential handling in code

Credentials are read from the environment only. They are never accepted as
function arguments, never written to disk, never included in a log line, and
never included in a repr — provider classes override `__repr__` for that reason.
Diagnostics report only *whether* a credential is present.

Providers refuse to run against an unpinned model identifier, so an
unreproducible run cannot spend a single token.

## If a secret is committed

1. Revoke and rotate it immediately. Assume it is compromised the moment it is
   pushed.
2. Remove it from history and force the removal upstream.
3. Record the exposure window and assess whether any experimental result depended
   on the affected credential.
4. Re-run the privacy and secret scans before pushing again.
