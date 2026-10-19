# Live guard experiment (induced)

Generated: 20261019_165904. Model `gpt-4o-mini`. Prompts carry an explicit instruction to break the rule, so this proves detection and recovery, not the organic rate.

| Scenario | Query | Apps | Grounding viol/retry/flag | Structure viol/retry/flag | Result |
|---|---|---|---|---|---|
| G1 | python engineer london | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G1 | backend engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G1 | solutions engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G2 | python engineer london | 2 | 1/1/0 | 0/0/0 | recovered, final drafts clean |
| G2 | backend engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G2 | solutions engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G3 | python engineer london | 2 | 0/0/0 | 2/2/0 | recovered, final drafts clean |
| G3 | backend engineer | 2 | 0/0/0 | 2/2/0 | recovered, final drafts clean |
| G3 | solutions engineer | 2 | 1/1/0 | 2/2/0 | recovered, final drafts clean |
| G4 | python engineer london | 2 | 0/0/0 | 4/2/2 | flagged and shown in report |
| G4 | backend engineer | 2 | 0/0/0 | 4/2/2 | flagged and shown in report |
| G4 | solutions engineer | 2 | 0/0/0 | 4/2/2 | flagged and shown in report |
| G5 | python engineer london | 2 | 1/1/0 | 0/0/0 | recovered, final drafts clean |
| G5 | backend engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |
| G5 | solutions engineer | 2 | 0/0/0 | 0/0/0 | provocation did not take (guard not exercised) |

Estimated cost (list price): $0.0190
