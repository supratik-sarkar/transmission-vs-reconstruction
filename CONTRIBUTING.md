# Contributing

This is a research repository with a preregistered experimental boundary.

Before contributing:

1. Do not commit secrets, private source documents, or unpublished run outputs.
2. Do not change frozen experimental behavior after a binding freeze without a documented deviation/new preregistration version.
3. Add or update tests for every protocol-affecting code change.
4. Run `make check`.
5. Keep provider/model defaults unfrozen until the preregistration explicitly pins them.

Protocol-affecting pull requests should state whether they modify:

- sampling;
- prompts;
- source population;
- matcher/editor behavior;
- causal estimands;
- gate computation;
- exclusions;
- provider decoding.
