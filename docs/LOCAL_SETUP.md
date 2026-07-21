# Local setup

## Recommended: Docker Compose

Prerequisites: Docker Desktop/Engine with Compose v2 and at least 8 GB available RAM.

```bash
cp .env.example .env
# Replace secrets and local passwords
docker compose up --build
```

Services:

- frontend: `http://localhost:3000`
- backend/OpenAPI: `http://localhost:8000/docs`
- MinIO console: `http://localhost:9001`
- PostgreSQL, Redis and ClamAV are internal Compose services.

## Native backend

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-production.txt
export PYTHONPATH=backend
export DATABASE_URL='postgresql+psycopg://...'
cd backend && alembic upgrade head
uvicorn main:app --reload --port 8000
```

## Native frontend

```bash
cd frontend
npm ci --legacy-peer-deps
VITE_BACKEND_URL=http://localhost:8000 npm run dev
```

## First user

Development can use `/api/auth/bootstrap` once. Production must set
`ALLOW_DEV_BOOTSTRAP=false` and provision the owner through the controlled script
or an administrator operation. Privileged users must complete MFA.

## Official ITR schemas

```bash
python scripts/sync_official_itr_artifacts.py
```

Review `backend/rules/official/manifest.json` and commit the approved schema files
and hashes only after a tax-domain owner verifies them. Configure the approved
utility adapter through `ITR_UTILITY_VALIDATION_COMMAND`.
