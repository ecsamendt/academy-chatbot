from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class Classification(BaseModel):
    language: Literal["es", "en", "mixed"] = Field(description="Language of the question")
    topic: str = Field(description="Short topic slug in Spanish, e.g. financiamiento, precios, marketing")
    intent: str = Field(description="Short intent slug in English, e.g. business_loan, pricing_strategy")
    time_sensitive: bool = Field(description="True if the answer depends on current rates, deadlines or programs")
    sensitive: bool = Field(description="True for financial distress, bankruptcy, debt trouble or legal trouble")


class DraftAnswer(BaseModel):
    answer: str = Field(description="The reply to the member, in their language")
    cited_passage_ids: list[str] = Field(description="IDs like P1, P3 of the passages actually used")
    recommended_tool_id: str | None = Field(description="ID like T1 of a tool passage to recommend, or null")


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0

    def add(self, other: "Usage") -> None:
        self.tokens_in += other.tokens_in
        self.tokens_out += other.tokens_out


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    language: str
    segments: list[TranscriptSegment] = field(default_factory=list)


class LLMProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def classify(self, question: str) -> tuple[Classification, Usage]: ...

    def write_answer(self, system: str, user: str) -> tuple[DraftAnswer, Usage]: ...

    def transcribe(self, audio_path: str, language: str = "es", model: str | None = None) -> Transcript: ...
