# External release gates

These gates cannot be marked complete by source code alone.

| Gate | Evidence required | Owner |
|---|---|---|
| CA tax certification | Signed golden-case results and variance log | CA tax lead |
| Official utility compatibility | Current utility import/validation evidence | CA + QA |
| Penetration test | Independent report; no open critical/high findings | Security owner |
| Privacy/legal | Reviewed privacy notice, DPA, customer agreement, retention policy | Counsel |
| Vendor review | Model/cloud/subprocessor security and privacy approval | Security/privacy |
| Disaster recovery | Timed restore report against approved RPO/RTO | DevOps |
| Controlled pilot | 100–300 supported returns, parallel calculation and acceptance | Product + pilot firms |

The system must remain behind feature flags and mandatory CA approval until all
applicable gates have documented evidence.
