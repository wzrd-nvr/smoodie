#!/usr/bin/env bash
# Bootstrap GitHub labels, milestones, and initial issues for smoodie.
# Idempotent: labels use --force; milestones/issues are skipped if a same-titled one exists.
set -euo pipefail

REPO="${REPO:-wzrd-nvr/smoodie}"

# ---------------------------------------------------------------- labels
echo "==> Labels"
label() { gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force >/dev/null; echo "  $1"; }

label "type:feature" "1D76DB" "New user-facing capability"
label "type:bug"     "D73A4A" "Something is broken"
label "type:chore"   "BFBFBF" "Maintenance, refactors, dependency bumps"
label "type:infra"   "5319E7" "Cloud infrastructure, IaC, deploys"
label "type:test"    "0E8A16" "Testing pipelines and coverage work"
label "type:docs"    "0075CA" "Documentation, ADRs, runbooks"
label "type:spike"   "FBCA04" "Time-boxed research / experiment"

label "area:web"      "C2E0C6" "React Router 7 frontend"
label "area:api"      "A2D2A4" "FastAPI backend"
label "area:db"       "82C482" "Postgres schema / migrations"
label "area:infra"    "62B662" "GCP resources / Terraform"
label "area:pipeline" "42A842" "Event collection, outbox, Pub/Sub, BigQuery"
label "area:auth"     "2E8B57" "Firebase Auth / sessions"
label "area:media"    "9BE0B0" "Uploads, GCS, images"
label "area:reviews"  "7FD8A0" "Two-tier critique review system"
label "area:ci"       "5FCB8F" "GitHub Actions workflows"

label "prio:P0" "B60205" "Blocks the milestone"
label "prio:P1" "D93F0B" "Important, do this milestone"
label "prio:P2" "E99695" "Nice to have this milestone"
label "prio:P3" "FEF2C0" "Backlog"

label "phase:mvp"      "006B75" "Phase 1 MVP scope"
label "phase:post-mvp" "76428A" "Phase 2: cook mode, Tier 2, AI/ML"

# ------------------------------------------------------------ milestones
echo "==> Milestones"
existing_ms=$(gh api "repos/$REPO/milestones?state=all&per_page=100" -q '.[].title')
milestone() {
  if grep -qxF "$1" <<<"$existing_ms"; then echo "  $1 (exists)"; return; fi
  gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null
  echo "  $1"
}

milestone "M0 Foundations"                   "Walking skeleton: monorepo, CI, Terraform dev env, both services deployed to Cloud Run"
milestone "M1 Auth & Profiles"               "Firebase Auth session flow, profile CRUD, avatars, media upload"
milestone "M2 Posts & Recipes"               "Core schema, post CRUD, recipe listing requirements, composer, SEO detail pages"
milestone "M3 Reviews, Votes & Comments"     "Tier 0 saves + Tier 1 verdicts with v0 confidence, votes on discussions, threaded comments, follows"
milestone "M4 Data Pipeline"                 "Outbox -> Pub/Sub -> BigQuery live and queryable; event catalog v1; client beacons"
milestone "M5 MVP Launch Hardening"          "E2E golden-path suite, prod environment, gated deploys, runbook, seed data"
milestone "M6 Cook Mode & Full Gate A"       "Phase 2: live cook sessions (timers, checklist, multi-day), full cook-confidence model"
milestone "M7 Tier 2 Reports & Gate B"       "Phase 2: Cook's Report (JAR/CATA/execution), instrument unlock, calibration, reliability"
milestone "M8 AI Summaries & Review Aggregation" "Phase 2: Claude-powered comment summaries and review aggregates"
milestone "M9 ML Recipe Builder & Dataset Tooling" "Phase 2: query-driven recipe builder, training dataset research and curation"

# ---------------------------------------------------------------- issues
echo "==> Issues"
existing_issues=$(gh issue list --repo "$REPO" --state all --limit 200 --json title -q '.[].title')
issue() { # title, milestone, labels (csv), body
  if grep -qxF "$1" <<<"$existing_issues"; then echo "  $1 (exists)"; return; fi
  gh issue create --repo "$REPO" --title "$1" --milestone "$2" --label "$3" --body "$4" >/dev/null
  echo "  $1"
}

t() { # build a standard issue body: overview, acceptance criteria, testing checklist
  printf '## Overview\n%s\n\n## Acceptance criteria\n%s\n\n## Testing\n%s\n' "$1" "$2" "$3"
}

# ---- M0
issue "[infra] Scaffold monorepo (pnpm, uv, docker-compose)" "M0 Foundations" "type:chore,area:infra,prio:P0,phase:mvp" "$(t \
"Create the monorepo skeleton: pnpm workspaces, apps/web + apps/api, packages/shared, infra/terraform, scripts/, docs/, docker-compose with postgres:16 + Firebase Auth emulator + Pub/Sub emulator." \
"- [ ] pnpm-workspace.yaml resolves apps/web and packages/*
- [ ] apps/api managed by uv with ruff + mypy configured
- [ ] docker-compose up starts postgres, firebase emulator, pubsub emulator
- [ ] README documents local dev setup" \
"- [ ] CI placeholder runs lint on both apps
- [ ] docker-compose healthchecks pass")"

issue "[infra] Terraform baseline: projects, state, Artifact Registry, WIF" "M0 Foundations" "type:infra,area:infra,prio:P0,phase:mvp" "$(t \
"Terraform modules + envs/dev + envs/prod for smoodie-dev / smoodie-prod in us-central1: tfstate bucket, Artifact Registry docker repo, Workload Identity Federation for GitHub Actions (no SA keys), base APIs enabled." \
"- [ ] terraform apply in envs/dev creates state bucket, AR repo, WIF pool/provider, runtime service accounts
- [ ] GitHub Actions can auth via WIF and push to Artifact Registry
- [ ] envs/prod mirrors dev behind its own state" \
"- [ ] terraform validate + fmt clean in CI (infra-plan.yml)
- [ ] Plan output reviewed on PR before apply")"

issue "[ci] PR pipelines with coverage gates" "M0 Foundations" "type:infra,area:ci,prio:P0,phase:mvp" "$(t \
"Path-filtered PR workflows: ci-api.yml (ruff, mypy, pytest unit+integration against postgres:16 service container, 80% coverage gate) and ci-web.yml (eslint, tsc, vitest)." \
"- [ ] API workflow runs unit + integration tests with a real Postgres service container
- [ ] Coverage below 80% fails the API build
- [ ] Web workflow runs eslint + tsc + vitest
- [ ] Workflows are path-filtered so unrelated changes skip" \
"- [ ] Both workflows green on the scaffold PR
- [ ] Deliberately failing test fails the pipeline (verified once)")"

issue "[api] FastAPI skeleton + SQLAlchemy + Alembic" "M0 Foundations" "type:feature,area:api,prio:P0,phase:mvp" "$(t \
"FastAPI app with /healthz, pydantic-settings config, SQLAlchemy 2.0 async engine, Alembic baseline migration, Dockerfile." \
"- [ ] GET /healthz returns 200 with app+db status
- [ ] alembic upgrade head runs against compose Postgres
- [ ] Container builds and serves via uvicorn" \
"- [ ] Unit: config parsing
- [ ] Integration: healthz + migration smoke test in CI")"

issue "[web] React Router 7 SSR skeleton + Dockerfile" "M0 Foundations" "type:feature,area:web,prio:P0,phase:mvp" "$(t \
"React Router 7 framework-mode app: root layout, index route, server rendering, Dockerfile running the node server." \
"- [ ] / renders server-side (view-source shows content without JS)
- [ ] TypeScript strict, eslint configured
- [ ] Container builds and serves" \
"- [ ] Vitest smoke test for root loader
- [ ] tsc --noEmit in CI")"

issue "[infra] Dev env Cloud Run + Cloud SQL, first deploy" "M0 Foundations" "type:infra,area:infra,prio:P0,phase:mvp" "$(t \
"Terraform for Cloud Run smoodie-web + smoodie-api, Cloud SQL Postgres 16 (private IP, db-custom-1-3840), Secret Manager wiring, deploy.yml that builds, migrates (Cloud Run job), and deploys to dev on push to main." \
"- [ ] Both services reachable at Cloud Run URLs in smoodie-dev
- [ ] API connects to Cloud SQL via unix socket
- [ ] Alembic migration job runs before API deploy" \
"- [ ] Post-deploy smoke: healthz 200 from the live URL in the workflow
- [ ] Rollback procedure documented in docs/runbooks")"

# ---- M1
issue "[api] Firebase session cookie exchange + auth dependency" "M1 Auth & Profiles" "type:feature,area:api,area:auth,prio:P0,phase:mvp" "$(t \
"POST /v1/auth/session exchanges a Firebase ID token for an http-only session cookie (firebase-admin), upserts the users row (emits user_signed_up on first), DELETE logs out. get_current_user dependency for protected routes." \
"- [ ] Valid ID token -> session cookie + users row
- [ ] Invalid/expired token -> 401
- [ ] DELETE clears the cookie
- [ ] user_signed_up written to event_outbox on first exchange" \
"- [ ] Unit: token verification faked, upsert logic
- [ ] Integration: full exchange against Firebase Auth emulator; outbox row asserted")"

issue "[web] Signup/login/logout flows" "M1 Auth & Profiles" "type:feature,area:web,area:auth,prio:P0,phase:mvp" "$(t \
"Login/signup routes using the Firebase web SDK (email + Google), then POST /v1/auth/session and redirect. Logout action. session.server.ts helpers for loaders." \
"- [ ] Email + Google sign-in work against the emulator locally
- [ ] Session persists across SSR navigations
- [ ] Logout clears session and redirects" \
"- [ ] Vitest: session helpers, redirect logic
- [ ] Playwright: signup -> land authenticated (emulator)")"

issue "[api] Profile CRUD + username rules" "M1 Auth & Profiles" "type:feature,area:api,prio:P1,phase:mvp" "$(t \
"GET/PATCH /v1/users/me and GET /v1/users/{username}. Username: citext unique, 3-30 chars, [a-z0-9_], immutable-after-set policy decision documented." \
"- [ ] Username validation with clear field errors
- [ ] Public profile returns posts count and join date
- [ ] profile_updated emitted to outbox" \
"- [ ] Unit: username rule matrix
- [ ] Integration: CRUD + uniqueness conflict (409)")"

issue "[web] Profile page + settings" "M1 Auth & Profiles" "type:feature,area:web,prio:P1,phase:mvp" "$(t \
"/u/:username with tabs (posts, recipes) and /settings/profile (display name, bio, avatar via signed-URL upload)." \
"- [ ] Public profile SSR-renders without auth
- [ ] Settings form uses route actions with progressive enhancement
- [ ] Avatar upload completes the media flow" \
"- [ ] Vitest: profile loader/action
- [ ] Playwright: edit bio + avatar end-to-end (emulator + local GCS fake)")"

issue "[api] Media signed-URL upload flow" "M1 Auth & Profiles" "type:feature,area:api,area:media,prio:P1,phase:mvp" "$(t \
"POST /v1/media/uploads returns a V4 signed PUT URL + media id (status pending); POST /v1/media/{id}/complete verifies the object and marks ready. Private bucket smoodie-{env}-media." \
"- [ ] Only image mime types accepted; size cap enforced
- [ ] complete verifies object existence + records dims/bytes
- [ ] media_uploaded emitted to outbox" \
"- [ ] Unit: mime/size validation
- [ ] Integration: full flow against a GCS emulator/fake")"

# ---- M2
issue "[db] Core schema migration (incl. full review-system tables)" "M2 Posts & Recipes" "type:feature,area:db,prio:P0,phase:mvp" "$(t \
"Alembic migration for the full day-1 schema: users, follows, posts, recipes (versioned), recipe_ingredients, recipe_steps, media, post_media, comments, saves, post_votes, comment_votes, reviews, review_confidence, cook_sessions, review_attributes, recipe_review_axes, user_reliability, comment_summaries, review_aggregates, event_outbox. All CHECKs and indexes per the plan." \
"- [ ] Migration applies cleanly to fresh Postgres 16 with citext + pg_trgm
- [ ] CHECK constraints enforce recipe/review invariants at the DB layer
- [ ] Partial index on unpublished outbox rows" \
"- [ ] Integration: constraint matrix (each CHECK violated -> IntegrityError)
- [ ] Downgrade path tested once")"

issue "[api] Post CRUD, discriminated recipe/discussion schemas, recipe versioning" "M2 Posts & Recipes" "type:feature,area:api,prio:P0,phase:mvp" "$(t \
"GET /v1/posts (cursor pagination, type/sort/cuisine/dietary filters), POST /v1/posts (discriminated union), GET/PATCH/DELETE /v1/posts/{id}. Recipe PATCH bumps recipes.version and replaces ingredient/step sets atomically. Slug generation." \
"- [ ] Cursor pagination stable under inserts
- [ ] Recipe edit bumps version; reviews keep the version they pinned
- [ ] post_created / recipe_created (full snapshot) emitted to outbox" \
"- [ ] Unit: slug gen, pagination cursors
- [ ] Integration: every route incl. atomic ingredient/step replacement + outbox assertions")"

issue "[api] Enforce recipe listing requirements (validation matrix + tests)" "M2 Posts & Recipes" "type:feature,area:api,prio:P0,phase:mvp" "$(t \
"Pydantic enforcement of the recipe listing requirements: >=2 ingredients each (quantity+unit) or to_taste, >=2 steps (each >=10 chars), servings >=1, at least one of prep/cook time, >=1 photo at publish (drafts exempt). Rich per-field errors for the composer UI." \
"- [ ] Each rule produces a distinct, field-addressed error
- [ ] Drafts bypass the photo rule only
- [ ] Curated unit list validated (incl. count/to-taste semantics)" \
"- [ ] Unit: full validation matrix (the highest-value test file in the repo)
- [ ] Integration: publish blocked end-to-end until valid")"

issue "[web] Composer with dynamic recipe form" "M2 Posts & Recipes" "type:feature,area:web,prio:P0,phase:mvp" "$(t \
"/posts/new: discussion/recipe toggle; recipe form with dynamic ingredient rows (qty/unit/name/prep-note/optional/to-taste, group labels) and step rows; client validation mirroring the Pydantic rules; photo upload." \
"- [ ] Add/remove/reorder ingredient and step rows
- [ ] Server field errors map back onto the form
- [ ] Works without JS via route action (progressive enhancement)" \
"- [ ] Vitest: row state machine + validation messages
- [ ] Playwright: publish blocked until requirements met, then succeeds")"

issue "[web] Post detail: SSR, OG meta, Recipe JSON-LD" "M2 Posts & Recipes" "type:feature,area:web,prio:P0,phase:mvp" "$(t \
"/p/:id/:slug post detail: SSR, OpenGraph meta, schema.org Recipe JSON-LD for recipe posts, emits post_viewed. Renders make-again score, saves, votes (discussions), review list, comments." \
"- [ ] curl of a recipe page shows full HTML + valid JSON-LD without JS
- [ ] Slug mismatch 301s to canonical URL
- [ ] post_viewed emitted via loader" \
"- [ ] Vitest: meta/JSON-LD builders
- [ ] Playwright: Google Rich Results-shaped JSON-LD asserted")"

# ---- M3
issue "[api] Saves (Tier 0) + votes endpoints" "M3 Reviews, Votes & Comments" "type:feature,area:api,area:reviews,prio:P0,phase:mvp" "$(t \
"PUT/DELETE /v1/posts/{id}/save (separate saves table, non-scoring). PUT /v1/posts/{id}/vote and /v1/comments/{id}/vote with value 1|-1|0, denormalized vote_score/save_count." \
"- [ ] Save/vote idempotent; 0 clears a vote
- [ ] Votes only on discussion posts (recipes reject with clear error)
- [ ] post_saved / vote_cast emitted to outbox" \
"- [ ] Unit: idempotency + score math
- [ ] Integration: concurrent vote race keeps denormalized score correct")"

issue "[api] Cook claims + Tier 1 reviews + v0 confidence model" "M3 Reviews, Votes & Comments" "type:feature,area:api,area:reviews,prio:P0,phase:mvp" "$(t \
"POST /v1/posts/{id}/cook-claims (retroactive kind: optional photo + 2-3 recipe-derived plausibility questions), POST /v1/posts/{id}/reviews (make_again, fidelity, outcome, note<=280, swaps chips, photo, claim id). Server-side v0 cook_confidence (versioned in review_confidence, model_version v0): photo bonus, account-age penalty, claim-only ceiling ~0.55, 72h decay. Thresholds from config, never exposed. Gate copy never accuses." \
"- [ ] Review requires a claim; one active review per (user, recipe), re-review updates
- [ ] fidelity != as_written captures structured swaps; outcome=failed skips hedonics
- [ ] confidence < tier1_scoring_floor -> displayed as unverified, weight 0
- [ ] review_submitted + cook_claim_submitted emitted with confidence + model_version" \
"- [ ] Unit: v0 confidence scoring table (signal -> score matrix)
- [ ] Integration: full claim->review flow incl. threshold behavior + outbox assertions")"

issue "[api] Weighted Wilson aggregation + denormalized recipe score" "M3 Reviews, Votes & Comments" "type:feature,area:api,area:reviews,prio:P0,phase:mvp" "$(t \
"Aggregate make_again with weight = cook_confidence x user_reliability x recency_decay into a weighted Wilson lower bound; denormalize make_again_pct, wilson_lb, review_count on posts. major_change reviews weight 0 on canonical (variant annotation). Publish n, never a raw proportion." \
"- [ ] Aggregate recomputes on review create/update and confidence recompute
- [ ] major_change excluded from canonical score
- [ ] Feed 'top' sort uses wilson_lb" \
"- [ ] Unit: Wilson math golden values incl. weighting + n=0/1 edges
- [ ] Integration: end-to-end review -> score change asserted")"

issue "[web] Review flow UI (claim -> verdict -> chips) + vote/save widgets" "M3 Reviews, Votes & Comments" "type:feature,area:web,area:reviews,prio:P0,phase:mvp" "$(t \
"'I made this' flow: retroactive claim (photo + plausibility questions) then one-screen Tier 1 verdict (make_again / fidelity / outcome, conditional swap chips, failure branch). Save button on all posts, vote widget on discussions. Gate copy per the brief (never accuses, never shows thresholds)." \
"- [ ] One screen, no scrolling for the verdict form
- [ ] Unverified reviews render with the soft label copy
- [ ] Score displays as 'X% would make again (n)'" \
"- [ ] Vitest: flow state machine incl. failure branch
- [ ] Playwright: claim -> verdict -> aggregate updates")"

issue "[api] Threaded comments + counts" "M3 Reviews, Votes & Comments" "type:feature,area:api,prio:P1,phase:mvp" "$(t \
"GET/POST /v1/posts/{id}/comments, PATCH/DELETE /v1/comments/{id}; parent_comment_id threading (UI renders 2 levels), soft delete, denormalized comment_count." \
"- [ ] Threaded fetch ordered for 2-level rendering
- [ ] Soft-deleted comments show placeholder, keep thread shape
- [ ] comment_created emitted to outbox" \
"- [ ] Unit: thread ordering
- [ ] Integration: CRUD + count maintenance + outbox assertions")"

issue "[api] Follows" "M3 Reviews, Votes & Comments" "type:feature,area:api,prio:P2,phase:mvp" "$(t \
"PUT/DELETE /v1/users/{username}/follow, follower/following lists. follow_created/removed events." \
"- [ ] Self-follow rejected
- [ ] Lists paginated
- [ ] Events emitted to outbox" \
"- [ ] Integration: follow/unfollow idempotency + outbox assertions")"

# ---- M4
issue "[pipeline] Outbox publisher + Pub/Sub -> BigQuery subscription" "M4 Data Pipeline" "type:feature,area:pipeline,prio:P0,phase:mvp" "$(t \
"Publisher loop (asyncio task in the API) draining event_outbox to Pub/Sub topic smoodie-events; Terraform for the topic + BigQuery subscription writing smoodie_analytics.events (partitioned by DATE(occurred_at), clustered by event_type). At-least-once with idempotent event_id." \
"- [ ] Unpublished rows drain within seconds; published_at set
- [ ] Crash between publish and mark -> no event loss (dupe tolerated)
- [ ] Events visible in BigQuery in dev" \
"- [ ] Integration: publisher against Pub/Sub emulator incl. retry path
- [ ] Dev smoke: bq query returns freshly emitted events")"

issue "[pipeline] Event catalog v1 + /v1/events + BQ views" "M4 Data Pipeline" "type:feature,area:pipeline,prio:P0,phase:mvp" "$(t \
"Versioned JSON Schemas in packages/shared/events for the v1 catalog (user_signed_up ... recipe_query_submitted), mirrored Pydantic models, POST /v1/events for batched client events (rate-limited), authored BigQuery views per event type + dedupe view." \
"- [ ] Every emitted event validates against its schema in tests
- [ ] recipe_created carries the full ingredient/step snapshot (ML corpus)
- [ ] Views make each event type queryable without JSON gymnastics" \
"- [ ] Unit: schema<->Pydantic parity for every event type
- [ ] Integration: /v1/events batch validation + rate limit")"

issue "[web] Client beacons (page_view, search, recipe_query)" "M4 Data Pipeline" "type:feature,area:web,area:pipeline,prio:P1,phase:mvp" "$(t \
"Client-side beacon util batching page_view, search_performed, and recipe_query_submitted (any natural-language 'what should I cook' style query) to /v1/events. The recipe_query stream is the phase-2 recipe-builder training signal - log from day 1." \
"- [ ] Batched + flushed on visibilitychange
- [ ] No beacons block rendering
- [ ] Respects logged-out sessions (anonymous id)" \
"- [ ] Vitest: batching/flush logic
- [ ] Playwright: events land in the API during golden path")"

# ---- M5
issue "[test] E2E golden-path Playwright suite" "M5 MVP Launch Hardening" "type:test,area:ci,prio:P0,phase:mvp" "$(t \
"CI Playwright suite against the compose stack: signup -> create recipe (blocked until valid) -> publish -> claim cook -> Tier 1 review -> aggregate updates -> comment -> appears in feed; JSON-LD asserted; discussion vote path." \
"- [ ] Suite green in CI on every PR to main
- [ ] Flake rate < 1% over 20 runs
- [ ] Runs under 10 minutes" \
"- [ ] This issue IS the testing pipeline; acceptance = suite quality gates above")"

issue "[infra] Prod environment + gated deploy + runbook" "M5 MVP Launch Hardening" "type:infra,area:infra,prio:P0,phase:mvp" "$(t \
"Terraform envs/prod apply (smoodie-prod), deploy.yml prod path gated by GitHub Environment approval on version tags, seed script, launch runbook (rollback, incident basics, backup/restore check)." \
"- [ ] Tagged release deploys to prod after manual approval
- [ ] Cloud SQL automated backups verified restorable once
- [ ] Runbook in docs/runbooks reviewed" \
"- [ ] Post-deploy smoke suite against prod URLs
- [ ] Migration dry-run job against a prod clone")"

echo "==> Done"
