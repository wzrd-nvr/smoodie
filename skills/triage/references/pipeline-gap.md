# pipeline-gap

Symptom: events are not arriving in BigQuery, or are arriving wrong. Nothing
user-facing breaks, which is exactly why this class needs its own reference —
the loss is silent, permanent, and the events are the phase-2 training corpus.

This class exists because every failure in it has already happened once here.

Checks:

1. **Establish where the chain stops.** It is
   `event_outbox` row → publisher → Pub/Sub topic → BigQuery subscription →
   `smoodie_analytics.events`. Query the outbox first: if rows exist with
   `published_at IS NULL`, the publisher is the problem and Pub/Sub is not.
2. **A missing message is not an error.** A Pub/Sub BigQuery subscription drops
   messages silently when they target a column type it cannot write — no error,
   no dead letter, no metric. This is why `payload` is a `STRING` wrapped in
   `PARSE_JSON()` by the views and not a `JSON` column. If someone has changed a
   column type, that is the first suspect.
3. **Check the subscription's own IAM.** Table-scoped grants are destroyed with
   the table; the Terraform binds them with `replace_triggered_by` for that
   reason. A table replaced without the grant being recreated silently stops
   accepting writes.
4. **Duplicates are expected, not a bug.** Delivery is at-least-once and a single
   publish has been observed landing twice under one `event_id`. If a count is
   wrong in the *high* direction, check that the consumer dedupes on `event_id`
   before looking for a publisher loop.
5. **Verify by publishing.** A payload-free test event isolates transport from
   schema — that is how the JSON-column drop was found. Publishing a test event
   to the dev topic is a read-only-equivalent diagnostic and is fair game;
   anything touching prod is not.

Proposal: this class is almost never fixed by a code revert. The usual outcome
is a Terraform change (reviewed, human-applied) or a view change. Say which.

Provenance: (seed, unverified)
