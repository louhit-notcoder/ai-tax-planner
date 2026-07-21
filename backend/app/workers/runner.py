from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.database import SessionLocal
from app.db_models import BackgroundJob
from app.itr.schema_registry import OfficialSchemaRegistry
from app.config import get_settings

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("green_papaya.worker")


def now():
    return datetime.now(timezone.utc)


def process(job: BackgroundJob) -> dict:
    if job.job_type == "SYNC_ITR_SCHEMAS":
        settings = get_settings()
        registry = OfficialSchemaRegistry()
        artifacts = []
        for form, url in {
            "ITR_1": settings.official_itr1_schema_url,
            "ITR_2": settings.official_itr2_schema_url,
        }.items():
            artifact = registry.sync(form, url, "AY2026_27_V1.1")
            artifacts.append({"form": form, "path": str(artifact.path), "sha256": artifact.sha256})
        return {"artifacts": artifacts}
    if job.job_type == "HEALTH_CHECK":
        return {"ok": True, "processed_at": now().isoformat()}
    raise ValueError(f"Unsupported background job type: {job.job_type}")


def claim_one(db):
    query = (
        select(BackgroundJob)
        .where(
            BackgroundJob.status == "QUEUED",
            BackgroundJob.attempts < BackgroundJob.max_attempts,
            or_(BackgroundJob.run_after.is_(None), BackgroundJob.run_after <= now()),
        )
        .order_by(BackgroundJob.created_at.asc())
        .limit(1)
    )
    if db.bind and db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    job = db.scalar(query)
    if not job:
        return None
    job.status = "RUNNING"
    job.attempts += 1
    job.locked_at = now()
    db.commit()
    return job


def run_forever() -> None:
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    logger.info("Green Papaya worker started")
    while True:
        with SessionLocal() as db:
            job = claim_one(db)
            if not job:
                time.sleep(poll_seconds)
                continue
            try:
                result = process(job)
                job.status = "COMPLETED"
                job.result_json = result
                job.completed_at = now()
                job.error_message = None
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job %s failed", job.id)
                job.error_message = str(exc)[:4000]
                job.status = "FAILED" if job.attempts >= job.max_attempts else "QUEUED"
                job.locked_at = None
            db.commit()


if __name__ == "__main__":
    run_forever()
