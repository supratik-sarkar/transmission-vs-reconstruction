# Security model

The public codebase never reads credentials from files inside the Git checkout by default.

Preferred secret locations:

- macOS: `~/Desktop/handoff-fidelity/.env` with mode `0600`;
- Colab: Colab Secrets or environment variables;
- CI: repository secrets only for non-experimental integration tests, never production study credentials.

Raw SEC/source files and unpublished experimental outputs live under the private workspace.
