---
name: branch-check-merged
description: Check if a git branch has been merged into the default branch (supports squash-merge detection)
scope: common
args:
  - name: branch
    required: false
    description: branch name to check; defaults to current branch
---

# :branch-check-merged

Check if a git branch has been merged into the default branch (supports squash-merge detection).

## Instructions

Check if the specified branch (or current branch if not specified) has been merged into the default branch (usually `main` or `master`).

* If a `branch` argument is provided, check that branch.
* If no `branch` argument is provided, check the current branch.

Use `git` commands to determine merge status:

```sh
git branch --merged <default-branch> | grep -q "<branch-name>"
```

Or check for squash-merge by comparing commit messages:

```sh
git log <default-branch> --oneline --grep="<branch-name>"
```
