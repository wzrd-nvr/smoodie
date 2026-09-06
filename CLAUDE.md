# Agent rules

## Division of labor

- The agent gathers evidence, proposes, verifies, and communicates.
- Humans decide what to mitigate and when. Humans open and close incidents.
- Every claim in a diagnosis names the log line, metric, commit, or file it came
  from. An unsourced cause is a guess and must be labelled as one.

## Verification

`make verify` is the gate. It binds this repo's real commands, and CI calls the
same targets, so an agent and CI cannot disagree about what green means.

| Target | What it runs |
|---|---|
| `make verify` | everything below, plus `verify-infra` |
| `make verify-api` | what `ci-api.yml` runs |
| `make verify-web` | what `ci-web.yml` runs |
| `make verify-infra` | what `infra-plan.yml` runs |
| `make test-contract` | the tests that define correct: every router against a real Postgres, with event-outbox rows asserted, plus `alembic check` for model/migration drift |
| `make smoke` | a deployed environment; needs `SMOKE_API_URL` and `SMOKE_WEB_URL` |

`make verify` needs Postgres 16 on localhost:5432, `uv`, `terraform`, and Node
>= 22.23 — Node 24 lives at `~/.local/node24/bin` on this machine and must be on
PATH first, because the system Node is below React Router's floor.

Never edit a test to make it pass. Add tests; do not delete assertions, loosen a
matcher, or skip a test to get green. Retry budget is three attempts per failing
check, then stop and report what each attempt produced.

A green suite is not evidence about production. Several bugs here passed every
test and still shipped — see `lessons.md`. Verify against deployed dev when the
change touches configuration, deployment, or the event pipeline.

## Production

No writes to production systems. The agent's outputs are messages, `lessons.md`
entries, pull requests, and proposals. The enforced rule is the global
`~/.claude/hooks/guard.py`, which denies irreversible destruction and asks
before anything production-touching; a freeze stated in conversation is a
request that can be forgotten, the guard is not. If the guard blocks a command,
propose it as a PR or hand the user the command — do not route around it.

Prefer a revert over a fix-forward for any user-facing regression. There are no
feature flags in this system, so "put it behind a flag" is not an available
proposal; say so rather than inventing one. State the rollback path in one line
with every proposed change, and note explicitly when reverting the code does not
revert a migration.

## Memory

Read `lessons.md` before every investigation; append after every resolution.
Anything load-bearing lives in git, not in conversation. When a diagnosis turns
out wrong, fix the reference file that produced it.

## Tools

Skills name capabilities — metrics, logs, errors, code host. `STACK.md` is the
only file that binds a capability to a vendor. Naming a vendor inside a skill is
a bug: it makes the skill unportable and it goes stale silently.

## The layout

| File | What it decides | Who changes it |
|---|---|---|
| `skills/` | how work is done | humans; agent proposes, by PR |
| `ONCALL.md`, `policy/` | thresholds, routing, autonomy | humans only, by PR |
| `lessons.md` | what has been learned | agent appends, humans prune |
| `STACK.md` | which tool provides which capability | humans, by PR |

Current rung: **Reader** (`policy/autonomy.md`). The agent investigates,
proposes, verifies, and appends lessons. Nothing is autonomous, and moving up is
one named decision per action, never a blanket promotion.
