"""OpenAI implementation of LLMProvider.

Model names come from settings (.env), so they can be changed without code.
"""

from __future__ import annotations

from openai import OpenAI

from app.config import get_settings
from app.llm.base import Classification, DraftAnswer, Transcript, TranscriptSegment, Usage

CLASSIFY_INSTRUCTIONS = """\
Clasifica la pregunta de un miembro de una academia de negocios para emprendedores latinos en EE. UU.
- language: idioma de la pregunta (es, en o mixed para Spanglish).
- topic: tema corto en español (ej. financiamiento, precios, marketing, impuestos, ventas, contabilidad).
- intent: intención corta en inglés con guiones bajos (ej. business_loan, pricing_strategy, sales_script).
- time_sensitive: true si la respuesta depende de tasas, fechas límite o programas actuales.
- sensitive: true si hay angustia financiera, deudas impagables, bancarrota o problemas legales.
"""

# Generous ceiling: reasoning models count their thinking against this limit.
MAX_OUTPUT_TOKENS = 4000


def _usage(resp) -> Usage:
    u = getattr(resp, "usage", None)
    if u is None:
        return Usage()
    return Usage(tokens_in=u.input_tokens or 0, tokens_out=u.output_tokens or 0)


class OpenAIProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key or None)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = self.client.embeddings.create(model=self.settings.embedding_model, input=batch)
            out.extend(d.embedding for d in sorted(resp.data, key=lambda d: d.index))
        return out

    def classify(self, question: str) -> tuple[Classification, Usage]:
        resp = self.client.responses.parse(
            model=self.settings.classify_model,
            instructions=CLASSIFY_INSTRUCTIONS,
            input=question,
            text_format=Classification,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        return resp.output_parsed, _usage(resp)

    def write_answer(self, system: str, user: str) -> tuple[DraftAnswer, Usage]:
        resp = self.client.responses.parse(
            model=self.settings.answer_model,
            instructions=system,
            input=user,
            text_format=DraftAnswer,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
        return resp.output_parsed, _usage(resp)

    def transcribe(self, audio_path: str, language: str = "es", model: str | None = None) -> Transcript:
        model = model or self.settings.transcribe_model
        with open(audio_path, "rb") as f:
            if model == "whisper-1":
                resp = self.client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
                segs = [
                    TranscriptSegment(start=float(s.start), end=float(s.end), text=s.text.strip())
                    for s in (resp.segments or [])
                ]
                return Transcript(language=getattr(resp, "language", language) or language, segments=segs)
            # Newer transcription models return text only (no timestamps).
            # Useful for the accuracy benchmark, not for indexing.
            resp = self.client.audio.transcriptions.create(model=model, file=f, language=language)
            return Transcript(language=language, segments=[TranscriptSegment(0.0, 0.0, resp.text.strip())])
