# ITR export policy

V3 has separate schema-driven ITR-1 and ITR-2 export services. Production export
requires all of the following:

1. COMPLETE deterministic computation and immutable fact snapshot;
2. final CA computation approval;
3. matching eligible form;
4. locally pinned official schema with verified SHA-256 manifest;
5. zero official JSON-schema/product validation errors;
6. successful configured approved official-utility validation;
7. final CA export approval.

Without a pinned schema, export returns 503. Without utility validation it remains
`READY_FOR_UTILITY_VALIDATION`; only `APPROVED` snapshots can be downloaded as
filing artifacts. This intentionally distinguishes schema validity from portal
utility compatibility.
