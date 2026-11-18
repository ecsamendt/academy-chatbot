"""Answer pipeline tests with a fake model and fake search (no network, no database)."""

import json

from app.answer import ask, deep_link, format_timestamp
from app.auth import Member
from app.config import Settings
from app.llm.base import Classification, DraftAnswer, Usage
from app.retrieval import Hit, can_access, split_by_access

SETTINGS = Settings(match_strong=0.5, match_partial=0.35, top_k=6)
SECRET_LOCKED_TEXT = "TEXTO SECRETO DEL CURSO AVANZADO"


def hit(id, score, *, public=False, memberships=(), source_type="lesson", text=None, start=750):
    return Hit(
        id=id, source_type=source_type, source_id=str(100 + id), course_title="Finanzas 101",
        module_title="Módulo 4", lesson_title=f"Lección {id}",
        lesson_url=f"https://academy.example.com/leccion-{id}/", start_sec=start if source_type == "lesson" else None,
        end_sec=None, text=text or f"pasaje {id}", is_public=public, allowed_memberships=list(memberships),
        required_plan_label="Plan Pro", score=score,
    )


class FakeProvider:
    def __init__(self, draft=None, language="es"):
        self.draft = draft or DraftAnswer(answer="Respuesta.", cited_passage_ids=["P1"], recommended_tool_id=None)
        self.language = language
        self.prompts = []

    def classify(self, q):
        return Classification(language=self.language, topic="precios", intent="pricing_strategy",
                              time_sensitive=False, sensitive=False), Usage(10, 5)

    def embed(self, texts):
        return [[0.0] * 3 for _ in texts]

    def write_answer(self, system, user):
        self.prompts.append(system + "\n" + user)
        return self.draft, Usage(100, 50)


def search_returning(hits):
    def fn(member, emb, k):
        return split_by_access(member, hits)
    return fn


BASIC = Member(user_id="1", memberships=(10,), staff=False)


def test_access_rules():
    assert can_access(BASIC, True, [])
    assert can_access(BASIC, False, [10, 20])
    assert not can_access(BASIC, False, [20])
    assert not can_access(BASIC, False, [])  # no rule info = staff only
    assert can_access(Member("2", (), True), False, [])


def test_strong_match_cites_with_timestamp_link():
    provider = FakeProvider()
    resp, trace = ask(BASIC, "¿Cómo pongo precios?", provider,
                      search_returning([hit(1, 0.8, memberships=[10])]), SETTINGS)
    assert resp.layer == "own_content"
    assert resp.citations[0].url == "https://academy.example.com/leccion-1/?t=750"
    assert resp.citations[0].timestamp_label == "12:30"
    assert trace.usage.tokens_in == 110


def test_locked_content_never_reaches_model_or_member():
    hits = [hit(1, 0.9, memberships=[99], text=SECRET_LOCKED_TEXT), hit(2, 0.6, memberships=[10])]
    provider = FakeProvider()
    resp, _ = ask(BASIC, "pregunta", provider, search_returning(hits), SETTINGS)
    assert SECRET_LOCKED_TEXT not in "".join(provider.prompts)
    assert SECRET_LOCKED_TEXT not in json.dumps(resp.to_dict(), ensure_ascii=False)


def test_only_locked_match_gives_upsell_without_model_call():
    provider = FakeProvider()
    resp, _ = ask(BASIC, "pregunta", provider,
                  search_returning([hit(1, 0.9, memberships=[99], text=SECRET_LOCKED_TEXT)]), SETTINGS)
    assert resp.layer == "locked_upsell"
    assert resp.upsell.course == "Finanzas 101"
    assert resp.upsell.plan == "Plan Pro"
    assert provider.prompts == []
    assert SECRET_LOCKED_TEXT not in json.dumps(resp.to_dict(), ensure_ascii=False)


def test_invented_passage_ids_and_tools_are_dropped():
    draft = DraftAnswer(answer="x", cited_passage_ids=["P1", "P7", "P1"], recommended_tool_id="T9")
    resp, _ = ask(BASIC, "q", FakeProvider(draft), search_returning([hit(1, 0.8, public=True)]), SETTINGS)
    assert len(resp.citations) == 1
    assert resp.tool is None


def test_tool_recommendation():
    draft = DraftAnswer(answer="Usa la calculadora.", cited_passage_ids=[], recommended_tool_id="T1")
    hits = [hit(1, 0.7, public=True), hit(2, 0.6, public=True, source_type="tool")]
    resp, _ = ask(BASIC, "q", FakeProvider(draft), search_returning(hits), SETTINGS)
    assert resp.tool.name == "Lección 2"


def test_partial_and_no_match_layers():
    provider = FakeProvider()
    resp, _ = ask(BASIC, "q", provider, search_returning([hit(1, 0.4, public=True)]), SETTINGS)
    assert resp.layer == "partial"
    assert "Información general" in provider.prompts[0]

    resp, _ = ask(BASIC, "q", FakeProvider(), search_returning([hit(1, 0.1, public=True)]), SETTINGS)
    assert resp.layer == "no_match"
    assert "no lo cubrimos" in resp.answer


def test_english_question_gets_english_fallback():
    resp, _ = ask(BASIC, "q", FakeProvider(language="en"), search_returning([]), SETTINGS)
    assert resp.language == "en"
    assert "don't cover" in resp.answer


def test_deep_link_and_timestamp_format():
    assert deep_link("https://a.com/l/?ref=x&t=5", 90) == "https://a.com/l/?ref=x&t=90"
    assert deep_link("https://a.com/l/", None) == "https://a.com/l/"
    assert format_timestamp(3725) == "1:02:05"
    assert format_timestamp(59) == "0:59"
