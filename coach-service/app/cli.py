"""Command line for setup and Phase 0 checks.

    python -m app.cli migrate
    python -m app.cli ingest-lesson 123 [--force]
    python -m app.cli ingest-all [--force]
    python -m app.cli ingest-tools
    python -m app.cli benchmark 111111111 222222222 ...   # Vimeo IDs
    python -m app.cli ask "¿Cómo calculo mi precio?" --memberships 12 34
"""

from __future__ import annotations

import argparse
import json
import logging

from app.config import get_settings


def cmd_benchmark(video_ids: list[str], models: list[str]) -> None:
    """Phase 0: transcribe the same lessons with each model and save the text side by side
    for a human to review (business terms, names, Spanglish)."""
    from app.ingestion import audio, vimeo
    from app.llm import get_provider

    out_dir = get_settings().work_dir / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = get_provider()
    for vid in video_ids:
        video = vimeo.get_video(vid)
        mp3 = audio.extract_audio(video.download_url, out_dir / vid / "audio.mp3")
        for model in models:
            texts = []
            for part in audio.split_for_upload(mp3):
                t = provider.transcribe(str(part.path), language="es", model=model)
                texts.append(" ".join(s.text for s in t.segments))
            path = out_dir / vid / f"{model}.txt"
            path.write_text(f"# {video.name} ({vid}) - {model}\n\n" + "\n".join(texts), encoding="utf-8")
            print(f"wrote {path}")
    print(f"\nCompare the files in {out_dir} against what the instructor actually said.")


def cmd_ask(question: str, memberships: list[int], staff: bool) -> None:
    from app import retrieval
    from app.answer import ask
    from app.auth import Member
    from app.llm import get_provider

    member = Member(user_id="cli", memberships=tuple(memberships), staff=staff)
    resp, trace = ask(member, question, get_provider(), retrieval.search)
    print(json.dumps(resp.to_dict(), ensure_ascii=False, indent=2))
    print(f"\nlayer={resp.layer} top_score={trace.top_score:.3f} tokens={trace.usage}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    s = sub.add_parser("ingest-lesson"); s.add_argument("lesson_id", type=int); s.add_argument("--force", action="store_true")
    s = sub.add_parser("ingest-all"); s.add_argument("--force", action="store_true")
    sub.add_parser("ingest-tools")
    s = sub.add_parser("benchmark")
    s.add_argument("video_ids", nargs="+")
    s.add_argument("--models", nargs="+", default=["whisper-1", "gpt-4o-transcribe"])
    s = sub.add_parser("ask")
    s.add_argument("question")
    s.add_argument("--memberships", nargs="*", type=int, default=[])
    s.add_argument("--staff", action="store_true")
    args = p.parse_args()

    from app.db import run_migrations

    if args.cmd == "migrate":
        print("applied:", run_migrations() or "nothing new")
        return
    run_migrations()
    if args.cmd == "ingest-lesson":
        from app.ingestion.pipeline import ingest_lesson
        print(ingest_lesson(args.lesson_id, force=args.force))
    elif args.cmd == "ingest-all":
        from app.ingestion.pipeline import ingest_all
        print(ingest_all(force=args.force))
    elif args.cmd == "ingest-tools":
        from app.ingestion.pipeline import ingest_tools
        print(f"indexed {ingest_tools()} tools")
    elif args.cmd == "benchmark":
        cmd_benchmark(args.video_ids, args.models)
    elif args.cmd == "ask":
        cmd_ask(args.question, args.memberships, args.staff)


if __name__ == "__main__":
    main()
