"""Answer pipeline (spec: Answer pipeline). Phase 1 scope:

1. identify member (done by the route)      4. Layer 1: answer from accessible passages
2. (usage limits: Phase 2)                  5. Layer 2 web fallback: Phase 2
3. classify the question                    6. log the question event

The model only ever sees passages the member may access. Locked passages are
used solely to name the course in an upgrade prompt. Offers (Phase 3) are
chosen after this module returns and can never change the answer.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.auth import Member
from app.config import Settings, get_settings
from app.llm import DraftAnswer, LLMProvider, Usage
from app.retrieval import Hit, SearchResult

NO_MATCH_MESSAGE = {
    "es": "Esto no lo cubrimos todavía en la academia. Ya tomamos nota de tu pregunta para "
    "crear contenido sobre el tema. ¿Quieres preguntarme otra cosa sobre tu negocio?",
    "en": "We don't cover this in the academy yet. We've noted your question so we can create "
    "content on it. Is there something else about your business I can help with?",
}

UPSELL_MESSAGE = {
    "es": "¡Buena pregunta! Esto lo explicamos a fondo en el curso «{course}», que está incluido "
    "en {plan}. Si mejoras tu plan, tendrás acceso a la lección completa.",
    "en": "Great question! We cover this in depth in the course \"{course}\", included in {plan}. "
    "Upgrade your plan to get the full lesson.",
}

SYSTEM_PROMPT = """\
Eres "Socio", el coach de negocios de la academia Su Socio de Negocios. Ayudas a emprendedores \
latinos en EE. UU. con respuestas cortas, prácticas y cálidas, en el idioma del miembro \
(español por defecto; si escribe en inglés, responde en inglés).

Reglas:
- Basa tu respuesta SOLO en los pasajes de lecciones y herramientas que se te dan. No inventes \
títulos de lecciones, minutos ni enlaces; el sistema agrega los enlaces a partir de los IDs que cites.
- En cited_passage_ids pon los IDs (P1, P2...) de los pasajes que realmente usaste.
- Si una herramienta (T1, T2...) encaja con la pregunta, pon su ID en recommended_tool_id y \
menciónala por nombre en la respuesta.
- {partial_rule}
- Para temas legales, de impuestos o de préstamos específicos, da información general y sugiere \
consultar a un profesional.
- Nunca menciones socios comerciales, bancos patrocinadores ni ofertas.
- Máximo unas 180 palabras. Termina con un siguiente paso concreto: una lección, una herramienta \
o una pregunta de seguimiento.
"""

PARTIAL_RULE_STRONG = "Si los pasajes no cubren algo, dilo con honestidad en lugar de adivinar."
PARTIAL_RULE_PARTIAL = (
    "Los pasajes cubren la pregunta solo en parte. Responde primero con lo que dicen los pasajes; "
    "si agregas conocimiento general, ponlo en un párrafo aparte que empiece con "
    "\"Información general:\" (o \"General information:\" en inglés)."
)


@dataclass
class Citation:
    kind: str
    title: str
    course: str | None
    module: str | None
    url: str
    start_sec: int | None
    timestamp_label: str | None


@dataclass
class ToolLink:
    name: str
    url: str


@dataclass
class Upsell:
    course: str
    plan: str
    message: str


@dataclass
class AskResponse:
    question_id: str
    language: str
    layer: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    tool: ToolLink | None = None
    upsell: Upsell | None = None
    offers: list[dict] = field(default_factory=list)  # Phase 3: filled by the affiliate layer

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AskTrace:
    """Everything the event log needs that isn't in the response."""

    topic: str | None = None
    intent: str | None = None
    time_sensitive: bool | None = None
    sensitive: bool | None = None
    top_score: float | None = None
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0


def format_timestamp(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def deep_link(url: str, start_sec: int | None) -> str:
    """Lesson URL with ?t=<seconds>; the lesson-page script seeks the Vimeo player."""
    if start_sec is None:
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "t"] + [("t", str(int(start_sec)))]
    return urlunsplit(parts._replace(query=urlencode(query)))


def label_passages(hits: list[Hit]) -> tuple[dict[str, Hit], dict[str, Hit]]:
    lessons: dict[str, Hit] = {}
    tools: dict[str, Hit] = {}
    for h in hits:
        if h.source_type == "tool":
            tools[f"T{len(tools) + 1}"] = h
        else:
            lessons[f"P{len(lessons) + 1}"] = h
    return lessons, tools


def build_user_prompt(question: str, lessons: dict[str, Hit], tools: dict[str, Hit]) -> str:
    parts = [f"Pregunta del miembro:\n{question}\n", "Pasajes de lecciones:"]
    for pid, h in lessons.items():
        where = " > ".join(x for x in (h.course_title, h.module_title, h.lesson_title) if x)
        parts.append(f"[{pid}] ({where}, minuto {format_timestamp(h.start_sec)})\n{h.text}")
    if not lessons:
        parts.append("(ninguno)")
    parts.append("\nHerramientas de la academia:")
    for tid, h in tools.items():
        parts.append(f"[{tid}] {h.lesson_title}\n{h.text}")
    if not tools:
        parts.append("(ninguna)")
    return "\n\n".join(parts)


def assemble(
    question_id: str,
    language: str,
    layer: str,
    draft: DraftAnswer,
    lessons: dict[str, Hit],
    tools: dict[str, Hit],
) -> AskResponse:
    """Turn the model's draft into the response. Links come only from our own records:
    IDs the model invents are dropped."""
    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()
    for pid in draft.cited_passage_ids:
        h = lessons.get(pid)
        if h is None or (h.source_id, h.start_sec) in seen:
            continue
        seen.add((h.source_id, h.start_sec))
        citations.append(
            Citation(
                kind="lesson",
                title=h.lesson_title,
                course=h.course_title,
                module=h.module_title,
                url=deep_link(h.lesson_url, h.start_sec),
                start_sec=h.start_sec,
                timestamp_label=format_timestamp(h.start_sec),
            )
        )
    tool = None
    if draft.recommended_tool_id and draft.recommended_tool_id in tools:
        t = tools[draft.recommended_tool_id]
        tool = ToolLink(name=t.lesson_title, url=t.lesson_url)
    return AskResponse(
        question_id=question_id,
        language=language,
        layer=layer,
        answer=draft.answer.strip(),
        citations=citations,
        tool=tool,
    )


def choose_layer(result: SearchResult, settings: Settings) -> str:
    if result.top_accessible >= settings.match_strong:
        return "own_content"
    if result.top_accessible >= settings.match_partial:
        return "partial"
    if result.top_locked >= settings.match_strong:
        return "locked_upsell"
    return "no_match"


def answer_language(lang: str) -> str:
    return "en" if lang == "en" else "es"


def ask(
    member: Member,
    question: str,
    provider: LLMProvider,
    search_fn,
    settings: Settings | None = None,
) -> tuple[AskResponse, AskTrace]:
    """search_fn(member, embedding, k) -> SearchResult; injected so tests can fake the DB."""
    settings = settings or get_settings()
    started = time.monotonic()
    trace = AskTrace()
    question_id = str(uuid.uuid4())

    cls, u = provider.classify(question)
    trace.usage.add(u)
    trace.topic, trace.intent = cls.topic, cls.intent
    trace.time_sensitive, trace.sensitive = cls.time_sensitive, cls.sensitive
    lang = answer_language(cls.language)

    [embedding] = provider.embed([question])
    result: SearchResult = search_fn(member, embedding, settings.top_k)
    trace.top_score = result.top_accessible
    layer = choose_layer(result, settings)

    if layer == "locked_upsell":
        best = max(result.locked, key=lambda h: h.score)
        course = best.course_title or best.lesson_title
        plan = best.required_plan_label or ("un plan superior" if lang == "es" else "a higher plan")
        resp = AskResponse(
            question_id=question_id,
            language=lang,
            layer=layer,
            answer=UPSELL_MESSAGE[lang].format(course=course, plan=plan),
            upsell=Upsell(course=course, plan=plan, message=UPSELL_MESSAGE[lang].format(course=course, plan=plan)),
        )
    elif layer == "no_match":
        resp = AskResponse(question_id=question_id, language=lang, layer=layer, answer=NO_MATCH_MESSAGE[lang])
    else:
        usable = [h for h in result.accessible if h.score >= settings.match_partial]
        lessons, tools = label_passages(usable)
        system = SYSTEM_PROMPT.format(
            partial_rule=PARTIAL_RULE_STRONG if layer == "own_content" else PARTIAL_RULE_PARTIAL
        )
        draft, u = provider.write_answer(system, build_user_prompt(question, lessons, tools))
        trace.usage.add(u)
        resp = assemble(question_id, lang, layer, draft, lessons, tools)

    trace.latency_ms = int((time.monotonic() - started) * 1000)
    return resp, trace
