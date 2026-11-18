"""HTTP interface of the coach service (spec: Service interfaces v1)."""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app import events, jobs, retrieval
from app.answer import ask
from app.auth import Member, current_member, require_admin, verified_webhook_body
from app.config import get_settings
from app.db import get_pool, run_migrations
from app.llm import get_provider

log = logging.getLogger("coach")


@asynccontextmanager
async def lifespan(_: FastAPI):
    applied = run_migrations()
    if applied:
        log.info("applied migrations: %s", applied)
    yield


app = FastAPI(title="Socio AI Coach", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class FeedbackBody(BaseModel):
    question_id: uuid.UUID
    value: Literal[1, -1]


class ClickBody(BaseModel):
    question_id: uuid.UUID | None = None
    kind: Literal["lesson", "tool", "upgrade"]
    target: str = Field(max_length=500)


class ContentWebhook(BaseModel):
    event: Literal["lesson.published", "lesson.updated", "lesson.deleted"]
    lesson_id: int


class ReindexBody(BaseModel):
    lesson_id: int | None = None
    all: bool = False
    tools: bool = False


@app.get("/health")
def health() -> dict:
    with get_pool().connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


@app.get("/me")
def me(member: Member = Depends(current_member)) -> dict:
    """Phase 0 check: proves the service can verify a member and read their plans."""
    return {"member_ref": member.ref, "memberships": list(member.memberships), "staff": member.staff}


@app.post("/ask")
async def ask_route(body: AskBody, member: Member = Depends(current_member)) -> dict:
    def run():
        resp, trace = ask(member, body.question.strip(), get_provider(), retrieval.search)
        try:
            events.log_question(member, body.question.strip(), resp, trace)
        except Exception:  # logging must never break an answer
            log.exception("failed to log question event")
        return resp.to_dict()

    return await run_in_threadpool(run)


@app.post("/feedback")
def feedback(body: FeedbackBody, member: Member = Depends(current_member)) -> dict:
    if not events.log_feedback(member, str(body.question_id), body.value):
        raise HTTPException(status_code=404, detail="question not found")
    return {"ok": True}


@app.post("/click")
def click(body: ClickBody, member: Member = Depends(current_member)) -> dict:
    events.log_click(member, str(body.question_id) if body.question_id else None, body.kind, body.target)
    return {"ok": True}


@app.post("/webhooks/content")
async def content_webhook(raw: bytes = Depends(verified_webhook_body)) -> dict:
    evt = ContentWebhook.model_validate(json.loads(raw))
    kind = "delete_lesson" if evt.event == "lesson.deleted" else "ingest_lesson"
    job_id = jobs.enqueue(kind, {"lesson_id": evt.lesson_id})
    return {"queued": job_id}


@app.post("/webhooks/memberpress")
async def memberpress_webhook(_: bytes = Depends(verified_webhook_body)) -> dict:
    # Phase 2: refresh cached access and usage limits. Phase 1 reads memberships
    # from the signed token on every request, so nothing is cached yet.
    return {"ok": True}


@app.post("/admin/reindex", dependencies=[Depends(require_admin)])
def reindex(body: ReindexBody) -> dict:
    queued = []
    if body.lesson_id is not None:
        queued.append(jobs.enqueue("ingest_lesson", {"lesson_id": body.lesson_id, "force": True}))
    if body.all:
        queued.append(jobs.enqueue("ingest_all", {"force": False}))
    if body.tools:
        queued.append(jobs.enqueue("ingest_tools"))
    if not queued:
        raise HTTPException(status_code=400, detail="nothing to re-index")
    return {"queued": queued}


@app.get("/admin/lessons", dependencies=[Depends(require_admin)])
def lesson_status() -> list[dict]:
    with get_pool().connection() as conn:
        return conn.execute(
            "SELECT lesson_id, title, status, detail, passage_count, updated_at FROM lessons ORDER BY title"
        ).fetchall()
