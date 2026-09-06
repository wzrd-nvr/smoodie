# Autonomy ladder

| Rung | Agent may | Unlock criteria |
|---|---|---|
| 1 Reader | investigate, propose, verify, append lessons | default |
| 2 Review | open fix/revert PRs, draft ramp plans | shadow-mode agreement >= 70% on holdouts, zero harmful proposals |
| 3 Narrow autonomous | execute ONE named action for ONE failure class (e.g. ramp-down on abort metric) | reference file exists, 10+ correct proposals for that class, deterministic abort, named human owner, audit log |

Each rung-3 action is its own decision with its own owner. There is no
rung 4. Permission level and run mode matter more than prompt quality.
