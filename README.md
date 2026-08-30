# smoodie

A forum-style community for eating, drinking, and cooking. Structured recipe sharing,
a two-tier verified review system ("% would make again", never stars), votes on
discussions, and a day-1 data pipeline feeding the phase-2 AI/ML features.

- **Web**: React Router (framework mode, SSR) → Cloud Run
- **API**: FastAPI + SQLAlchemy + Alembic → Cloud Run
- **Data**: Cloud SQL Postgres 16 + outbox → Pub/Sub → BigQuery
- **Auth**: Firebase Auth (session cookies)
- **Infra**: Terraform, `smoodie-dev` / `smoodie-prod`, us-central1

Key docs: [`docs/review-system.html`](docs/review-system.html) (review system spec) ·
[`packages/shared/events/`](packages/shared/events/) (event catalog).
Work is tracked in [GitHub Issues](https://github.com/wzrd-nvr/smoodie/issues) —
labels `type:* area:* prio:* phase:*`, milestones M0–M9.

## Local development

Prereqs: Node ≥ 22.23, [pnpm](https://pnpm.io) (via `corepack enable`),
[uv](https://docs.astral.sh/uv/), Docker.

```sh
docker compose up -d          # postgres:16, Firebase Auth emulator, Pub/Sub emulator

pnpm install
pnpm dev:web                  # web on http://localhost:5173

cd apps/api
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn smoodie_api.main:app --reload --port 8000
```

## Checks

```sh
pnpm --filter web typecheck && pnpm --filter web test && pnpm --filter web lint

cd apps/api
uv run ruff check src tests && uv run mypy && uv run pytest --cov
```

Every feature ships with unit + integration tests enforced in CI — no exceptions.
