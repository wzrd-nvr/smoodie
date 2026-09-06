---
name: triage
description: Investigate an alert or incident and post a grounded diagnosis with evidence links and a proposed mitigation.
---

1. Read `lessons.md`. Note any matching symptom from the last 30 days.
2. Classify the symptom into one failure class in `references/`. If none fits, say so and investigate generically.
3. Load that reference file and follow its checks in order.
4. Correlate: recent deploys, flag changes, config changes, dependency status.
5. Post a SITREP:
   - **Symptom** (with link)
   - **Evidence** (each claim linked)
   - **Likely cause** with confidence (high / medium / low)
   - **Proposed mitigation**: revert PR, flag ramp-down plan, or "needs human judgment"
   - **What would change my mind**
6. If a human pushes back, test their hypothesis against the data and report either way.
7. After a fix lands, poll the affected metric until baseline and confirm in-thread.
8. Append to `lessons.md`.

Never: close the incident, touch a flag, run a migration, or edit tests.
