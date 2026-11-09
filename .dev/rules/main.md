# Repository rules (basic template)

This repo started empty. Extend these rules when you add languages, frameworks, or CI.

## Documentation

* Prefer [Markdown conventions](../libs/markdown.md) for `README.md`, `docs/`, and `.dev/`.
* Keep `README.md`, TechDocs (`docs/` + `mkdocs.yml`), and `catalog-info.yaml` descriptions consistent.

## Git & changes

* Use meaningful branch names and commit messages.
* Prefer small, reviewable changes.

## Security & ownership

* Respect `security/data-classification` and ownership in `catalog-info.yaml`.
* Do not commit secrets; use your org’s secret management.

## When you add a stack

* Document tooling in `README.md` (install, run, test).
* Add stack-specific lint/format rules here (or split into `.dev/rules/<stack>.md` and link from this file).
