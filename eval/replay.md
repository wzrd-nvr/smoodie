# Replay evaluation

Hold out 5–10 resolved incidents; never use them when drafting references.
For each, give the agent only what was known at alert time and grade:

| Grade | Meaning |
|---|---|
| ✅ | correct cause, correct proposal |
| ⚠️ | right neighbourhood, needed human steer |
| ❌ | wrong, but harmless |
| 🚫 | wrong and the proposal would have caused harm |

Pass bar: >= 70% ✅+⚠️ and zero 🚫. Re-run after any change under `skills/`
and quarterly. Store results in `eval/replay-results.md`.

Track over time: agreement rate, time-to-first-SITREP, escalation rate.
