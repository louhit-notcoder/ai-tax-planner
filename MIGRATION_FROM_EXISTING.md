# Migration from the existing Green Papaya project

## Do not overwrite the old directory

1. Stop the old backend/frontend.
2. Create encrypted backups of the old database and object/document directory.
3. Record the current commit/archive hash and environment variables.
4. Extract V3 into a new directory, for example `green-papaya-v3-production`.
5. Configure a new PostgreSQL database and object-storage bucket.
6. Run Alembic migrations.
7. Import only reviewed tenant/client/case/document metadata through the migration
   script; never point V3 at the old Mongo database as its live system of record.
8. Run both systems in parallel using anonymised cases before controlled cutover.
9. Keep the old system read-only until reconciliation and backup restoration pass.

## Commands

```bash
cp .env.example .env
cd backend
alembic upgrade head
cd ..
python scripts/migrate_legacy_mongo_to_postgres.py --help
python scripts/provision_firm_owner.py --help
```

The legacy import script requires the optional packages in
`scripts/requirements-legacy-migration.txt`. It imports records as reviewable data;
it must not auto-approve legacy parsed values.

## Breaking changes

- MongoDB is not the V3 source of truth.
- self-selected privileged roles are removed;
- all material writes require tenant/case authorization;
- parsed data becomes candidate facts, not computation input;
- computations are snapshot-based and immutable;
- final export requires schema validation, utility validation and CA approval;
- the active server is `backend/main.py`, not `server.py`.
