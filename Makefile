# The single verification surface. CI is a thin wrapper over these targets, so
# an agent and CI cannot disagree about what "green" means.
#
# Toolchain: uv (API), pnpm on Node >= 22.23 (web), terraform (infra), and a
# local Postgres 16 for the contract target. Node 24 lives at
# ~/.local/node24/bin on this machine and must be on PATH before `make test`.

.PHONY: verify lint typecheck test test-contract build smoke \
        lint-api lint-web typecheck-api typecheck-web test-api test-web \
        verify-api verify-web verify-infra

API := apps/api
WEB := apps/web

# ------------------------------------------------------------------ verify
# Everything a change must pass before it is proposed. Deliberately stricter
# than any single CI job: the per-app workflows are path-filtered, this is not.
verify: lint typecheck test test-contract build verify-infra

# The groupings the path-filtered workflows call, so CI and this file stay bound.
verify-api: lint-api typecheck-api test-api test-contract
verify-web: lint-web typecheck-web test-web build

# ------------------------------------------------------------------- lint
lint: lint-api lint-web

lint-api:
	cd $(API) && uv run ruff check src tests alembic
	cd $(API) && uv run ruff format --check src tests alembic

lint-web:
	pnpm --filter web lint

# -------------------------------------------------------------- typecheck
typecheck: typecheck-api typecheck-web

typecheck-api:
	cd $(API) && uv run mypy

# react-router typegen runs first; route module types do not exist without it.
typecheck-web:
	pnpm --filter web typecheck

# ------------------------------------------------------------------- test
# Unit tests only: no database, no network. Fast enough to run on every edit.
test: test-api test-web

test-api:
	cd $(API) && uv run pytest tests/unit

test-web:
	pnpm --filter web test

# --------------------------------------------------------- test-contract
# The tests that define correct rather than merely passing: every router
# exercised against a real Postgres, with the event-outbox rows asserted for
# each mutating endpoint. `alembic check` is here too because a model that has
# drifted from its migration is a correctness failure that no test would catch —
# the suite builds its schema from the models, the deployed database from the
# migrations, and only this compares them.
#
# Requires Postgres on localhost:5432 (see docker-compose.yml). The coverage
# gate runs over the whole suite here, which re-runs the unit tests; that is
# deliberate, so this target is meaningful when run on its own.
test-contract:
	cd $(API) && uv run alembic upgrade head
	cd $(API) && uv run alembic check
	cd $(API) && uv run pytest --cov --cov-fail-under=80

# ------------------------------------------------------------------ build
build:
	pnpm --filter web build

# ------------------------------------------------------------ verify-infra
verify-infra:
	cd infra/terraform && terraform fmt -check -recursive
	cd infra/terraform && terraform -chdir=envs/dev init -backend=false -input=false
	cd infra/terraform && terraform -chdir=envs/dev validate
	cd infra/terraform && terraform -chdir=envs/prod init -backend=false -input=false
	cd infra/terraform && terraform -chdir=envs/prod validate

# ------------------------------------------------------------------ smoke
# Runs against a deployed environment, so it belongs after a deploy, not on a
# pull request: there are no per-PR preview environments, and pointing this at
# dev from a PR would assert things about main's deployment instead of the
# change under review. deploy.yml calls it once dev is live.
SMOKE_API_URL ?=
SMOKE_WEB_URL ?=

# Each response is captured whole before it is matched. Piping curl into
# `grep -q` looks equivalent and is not: grep exits at the first match, closes
# the pipe, and curl dies with "(23) Failure writing output to destination",
# then retries the whole request five times on a body it already received.
smoke:
	@test -n "$(SMOKE_API_URL)" || { echo "SMOKE_API_URL is unset"; exit 1; }
	@test -n "$(SMOKE_WEB_URL)" || { echo "SMOKE_WEB_URL is unset"; exit 1; }
	@echo "api: $(SMOKE_API_URL)"
	@echo "web: $(SMOKE_WEB_URL)"
	@health="$$(curl -fsS --retry 5 --retry-delay 5 --retry-all-errors "$(SMOKE_API_URL)/health")"; \
	  echo "health: $$health"; \
	  case "$$health" in \
	    *'"database":"ok"'*) ;; \
	    *) echo "API cannot reach Cloud SQL"; exit 1 ;; \
	  esac
	@body="$$(curl -fsS --retry 5 --retry-delay 5 --retry-all-errors "$(SMOKE_WEB_URL)/")"; \
	  case "$$body" in \
	    *[Ss]moodie*) ;; \
	    *) echo "web did not render"; exit 1 ;; \
	  esac
