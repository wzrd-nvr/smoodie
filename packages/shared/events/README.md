# Event catalog

Versioned JSON Schemas for every event smoodie emits — the source of truth for the
outbox → Pub/Sub → BigQuery pipeline. Each event lives at `<event_type>/v<version>.json`.
The API mirrors these as Pydantic models; parity is asserted in tests
(see issue "[pipeline] Event catalog v1").

Envelope (every event, enforced by the outbox writer):

| field | type | notes |
|---|---|---|
| event_id | uuid | idempotency key in BigQuery |
| event_type | string | e.g. `recipe_created` |
| schema_version | int | matches the schema file version |
| actor_id | uuid \| null | acting user |
| entity_type / entity_id | string / uuid | subject of the event |
| occurred_at | timestamp | event time, not publish time |
| payload | object | validates against the schema here |

Two things the pipeline forces on the publisher, both learned by testing against
real infrastructure (see `infra/terraform/README.md`):

- `payload` is published as a **JSON string**, not a nested object. The BigQuery
  column is `STRING` because a Pub/Sub BigQuery subscription silently drops
  messages targeting a `JSON`-typed column. Views wrap it in `PARSE_JSON()`.
- Delivery is **at-least-once and duplicates were observed in practice** — a
  single publish landed twice under the same `event_id`. Every view and consumer
  must dedupe on `event_id`.

v1 catalog: `user_signed_up, profile_updated, follow_created, follow_removed,
post_created, recipe_created, post_viewed, post_saved, vote_cast, review_submitted,
review_confidence_recomputed, cook_claim_submitted, comment_created, media_uploaded,
search_performed, recipe_query_submitted`.

`recipe_created` carries the full ingredient/step snapshot and
`recipe_query_submitted` captures natural-language "what should I cook" queries —
together these are the phase-2 ML training corpus. Log them scrupulously.
