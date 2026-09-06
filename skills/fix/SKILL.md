---
name: fix
description: Author a minimal, revertible fix PR for a diagnosed issue.
---

Preconditions: a triage SITREP with high or medium confidence, and the
thresholds in `policy/errors.md` are met.

1. Write a failing test that reproduces the issue. If you cannot, stop and say why.
2. Make the smallest change that passes it. No drive-by refactors.
3. `make verify`. Retry budget: 3. Then escalate.
4. Open a PR using the template. Link the error group and SITREP. State the rollback in one line.
5. Do not merge. Do not request review from yourself.
