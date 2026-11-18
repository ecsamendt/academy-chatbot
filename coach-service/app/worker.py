"""Background worker: runs ingestion jobs queued by webhooks and the admin re-index button.

    python -m app.worker
"""

from __future__ import annotations

import logging
import time
import traceback

from app import jobs
from app.db import run_migrations
from app.ingestion import pipeline

log = logging.getLogger("coach.worker")

HANDLERS = {
    "ingest_lesson": lambda p: pipeline.ingest_lesson(int(p["lesson_id"]), force=bool(p.get("force"))),
    "delete_lesson": lambda p: pipeline.delete_lesson(int(p["lesson_id"])),
    "ingest_all": lambda p: pipeline.ingest_all(force=bool(p.get("force"))),
    "ingest_tools": lambda p: pipeline.ingest_tools(),
}


def run_forever(poll_seconds: float = 5.0) -> None:
    run_migrations()
    jobs.requeue_stuck()
    log.info("worker started")
    while True:
        job = jobs.claim_next()
        if job is None:
            time.sleep(poll_seconds)
            continue
        log.info("job %s %s %s", job["id"], job["kind"], job["payload"])
        try:
            handler = HANDLERS[job["kind"]]
            result = handler(job["payload"])
            jobs.finish(job["id"])
            log.info("job %s done: %s", job["id"], result)
        except Exception:
            err = traceback.format_exc()
            log.error("job %s failed: %s", job["id"], err)
            jobs.fail(job["id"], job["attempts"], err)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_forever()
