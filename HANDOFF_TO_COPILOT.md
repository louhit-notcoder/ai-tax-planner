# Handoff to your local setup copilot

## Safe replacement decision

Do **not** overwrite the current project directory. Extract V3 beside it, keep the old
system read-only, and migrate reviewed data only after backup and reconciliation.

Suggested directory:

```text
green-papaya-v3-production/
```

## First local commands

```bash
cp .env.example .env
# Fill every required value described in docs/INPUTS_REQUIRED.md
docker compose up --build
```

Then verify:

```bash
./scripts/run_checks.sh
cd backend && alembic current && alembic upgrade head
cd ../frontend && npm ci --legacy-peer-deps && npm run build
```

Open:

- frontend: `http://localhost:3000`
- API/OpenAPI: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`

## Before export testing

```bash
python scripts/sync_official_itr_artifacts.py
python scripts/check_official_updates.py
```

Review and approve the downloaded schema hashes. Configure
`ITR_UTILITY_VALIDATION_COMMAND` only for a documented approved utility-validation
workflow. A schema-valid payload is not automatically portal/utility certified.

## Before model testing

Set an approved provider/model, then run:

```bash
OPENROUTER_API_KEY=... OPENROUTER_ASSISTANT_MODEL=... \
python scripts/evaluate_model.py --online --output model-evaluation.json
```

Do not use real taxpayer data during initial model evaluation.

## Legacy migration

```bash
pip install -r scripts/requirements-legacy-migration.txt
python scripts/migrate_legacy_mongo_to_postgres.py --help
```

The importer creates reviewable records. It does not auto-approve legacy parser output.
Run both systems in parallel until case counts, documents and calculations reconcile.

## Production values the copilot must ask you for

- firm owner and firm name;
- production app/API domain;
- PostgreSQL/Redis/S3 credentials or cloud account;
- encryption, blind-index and JWT secrets;
- SMTP provider/sender;
- approved model/provider and retention/ZDR terms;
- CA tax lead and golden-case files;
- official utility validation method;
- retention/RPO/RTO/on-call contacts;
- privacy counsel and penetration-test contacts.
