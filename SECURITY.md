# Security and secret handling

Never commit API keys, SEC credentials, provider tokens, private data, or unpublished raw outputs.

The intended secret location is:

```text
~/Desktop/handoff-fidelity/.env
```

If a secret is accidentally committed:

1. revoke/rotate it immediately;
2. remove it from Git history;
3. document any effect on experimental integrity;
4. rerun secret scanning before pushing.

The repository's `.gitignore`, pre-commit hook, and CI secret scan are defense-in-depth, not substitutes for careful handling.
