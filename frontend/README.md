# Green Papaya V3 frontend

The active frontend is a React 19, TypeScript and Vite CA workbench.

```bash
npm ci --legacy-peer-deps
VITE_BACKEND_URL=http://localhost:8000 npm run dev
npm run build
```

Active routes:

- `/` — firm login;
- `/mfa` — privileged-user MFA enrollment/verification;
- `/dashboard` — firm case dashboard;
- `/cases/:id` — assistant, evidence, facts, reconciliation, computation, review and export workspace.

The API client uses HttpOnly cookie sessions with refresh handling. The browser does
not store access or refresh tokens in local storage. Legacy V2 pages/configuration
are retained only under `legacy_v2` and are outside the active Vite build.
