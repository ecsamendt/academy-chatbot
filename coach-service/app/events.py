"""Question and click event logging (spec: Insights and logging)."""

from __future__ import annotations

from app.answer import AskResponse, AskTrace
from app.auth import Member
from app.db import get_pool


def log_question(member: Member, question: str, resp: AskResponse, trace: AskTrace) -> None:
    cited_lessons = sorted({c.url.split("?")[0] for c in resp.citations})
    cited_tools = [resp.tool.name] if resp.tool else []
    with get_pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO question_events (
                question_id, member_ref, memberships, question, language, topic, intent,
                time_sensitive, sensitive, layer, top_score, cited_lessons, cited_tools,
                offers_shown, tokens_in, tokens_out, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                resp.question_id, member.ref, list(member.memberships), question, resp.language,
                trace.topic, trace.intent, trace.time_sensitive, trace.sensitive, resp.layer,
                trace.top_score, cited_lessons, cited_tools,
                [o.get("slug", "") for o in resp.offers],
                trace.usage.tokens_in, trace.usage.tokens_out, trace.latency_ms,
            ),
        )


def log_feedback(member: Member, question_id: str, value: int) -> bool:
    with get_pool().connection() as conn:
        cur = conn.execute(
            "UPDATE question_events SET feedback = %s WHERE question_id = %s AND member_ref = %s",
            (value, question_id, member.ref),
        )
        return cur.rowcount > 0


def log_click(member: Member, question_id: str | None, kind: str, target: str) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO click_events (question_id, member_ref, kind, target) VALUES (%s, %s, %s, %s)",
            (question_id, member.ref, kind, target),
        )
