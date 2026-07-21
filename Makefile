.PHONY: test backend frontend migrate schema-sync legal-sync up down clean syntax secrets

PYTHONPATH := backend

test:
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=$(PYTHONPATH) pytest -q backend/tests_v3

syntax:
	PYTHONPATH=$(PYTHONPATH) python -m compileall -q backend/app backend/main.py
	node scripts/check_frontend_syntax.js

secrets:
	python scripts/verify_no_embedded_secrets.py

backend:
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

migrate:
	cd backend && alembic upgrade head

schema-sync:
	python scripts/sync_official_itr_artifacts.py

legal-sync:
	python scripts/ingest_official_legal_sources.py

up:
	docker compose up --build

down:
	docker compose down

clean:
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
	find . -name '*.pyc' -delete
	rm -rf .pytest_cache frontend/dist
