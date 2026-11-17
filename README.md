# academy-chatbot — Socio AI Coach

A chat assistant inside academy.susociodenegocios.com that answers members' business
questions from our own lessons and tools, with links to the exact minute of the lesson.

This branch covers **Phase 0 (foundations)** and **Phase 1 (library coach, internal beta)**
from the product spec. Web-search fallback, usage limits, the insights dashboard (Phase 2)
and affiliate offers (Phase 3) come later.

## How it fits together

```
 WordPress (academy site)                         Coach service (AWS, Docker)
 ┌───────────────────────────────┐   question +   ┌─────────────────────────────────┐
 │ wp-plugin/socio-coach         │  member token  │ coach-service (FastAPI)         │
 │  • chat window [socio_coach]  │ ─────────────▶ │  POST /ask  → answer + links    │
 │  • signs member token         │                │  classify → search → write      │
 │  • lesson feed (REST)         │ ◀───────────── │  worker: Vimeo → transcribe →   │
 │  • "lesson changed" webhook   │ ─────────────▶ │          passages → embeddings  │
 │  • ?t= timestamp jump         │                │  Postgres + pgvector            │
 └───────────────────────────────┘                └─────────────────────────────────┘
```

WordPress stays light: it only hosts the chat window and tells the service who the member
is. Transcription and AI calls run on the coach service.

| Folder | What it is |
|---|---|
| `coach-service/` | Python 3.12, FastAPI, OpenAI, Postgres + pgvector. API and ingestion worker. |
| `coach-service/tools/tools.yaml` | Hand-written entries for the academy tools. **Edit the URLs and text.** |
| `wp-plugin/socio-coach/` | WordPress plugin. Zip this folder to install it. |
| `docker-compose.yml` | Runs the database, API and worker locally. |

## Answer rules built in

- The model only sees passages the member can access. Locked lessons are used only to name
  the course in an upgrade prompt; their text never leaves the server (covered by tests).
- Links and timestamps come from our records, not from the model. If the model cites a
  passage ID that doesn't exist, it's dropped.
- No usable match → a clear "we don't cover this yet" reply, logged as a content gap.
- Every question is logged with a pseudonymous member ID (no email), layer, topic and tokens.

## Run it locally

Needs [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env        # then fill in the secrets
docker compose up --build
```

The API is at http://localhost:8000 (`/health`, and interactive docs at `/docs`).

Useful commands (run inside the worker container: `docker compose exec worker ...`):

```bash
python -m app.cli ingest-tools                    # index tools/tools.yaml
python -m app.cli ingest-lesson 123               # one lesson by WordPress ID
python -m app.cli ingest-all                      # every published lesson
python -m app.cli ask "¿Cómo calculo mi precio?" --staff
python -m app.cli benchmark 111111111 222222222   # Phase 0 transcription comparison
```

Tests (no database or API key needed):

```bash
cd coach-service
pip install -e ".[dev]"
pytest
```

## Phase 0 checklist

1. **MemberPress Developer Tools** installed, and **a real server cron** replacing WP Cron
   (MemberPress sends webhooks through WP Cron; many hosts disable it).
2. **Secrets**: generate four long random strings (e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   for `MEMBER_TOKEN_SECRET`, `WEBHOOK_SECRET`, `WP_INGEST_SECRET`, `ADMIN_API_KEY`. Put them in
   the service's `.env` and in WordPress (Settings → Socio AI Coach, or as constants in
   `wp-config.php`: `SOCIO_COACH_MEMBER_TOKEN_SECRET`, `SOCIO_COACH_WEBHOOK_SECRET`,
   `SOCIO_COACH_INGEST_SECRET`, `SOCIO_COACH_ADMIN_API_KEY`).
3. **Vimeo token** with the `private` and `video_files` scopes (the account plan must allow
   API downloads).
4. **OpenAI API key**, and confirm the model names in `.env`.
5. **Install the plugin on staging**, then check:
   - `GET /wp-json/socio-coach/v1/lessons` with the `X-Socio-Ingest-Secret` header lists
     lessons with the right course, Vimeo ID and membership IDs. **Membership detection
     (`includes/class-access.php`) must be verified against our MemberPress version.**
   - Logged in, open a page with `[socio_coach]`; `GET /me` on the service (with the token
     from `/wp-json/socio-coach/v1/token`) shows your memberships.
6. **Transcription benchmark**: run `benchmark` on 5 real lessons and compare the text by
   hand (business terms, names, Spanglish). `whisper-1` is the default because it returns
   the segment timestamps the deep links need.

**Done when:** the service verifies a member's plan, and one lesson is transcribed accurately.

## Phase 1 checklist (internal beta)

- `ingest-tools`, then `ingest-all`. Check `GET /admin/lessons` (header `X-Admin-Key`) for
  lessons flagged `no_video` or `multiple_videos`. For a lesson with several videos, set a
  custom field `socio_coach_vimeo_id` on the lesson with the right ID and re-index it.
- Staff test questions in Spanish, English and Spanglish; tune `MATCH_STRONG` /
  `MATCH_PARTIAL` in `.env` from the `top_score` the `ask` command prints.
- Timestamp links on desktop **and iPhone** (iOS shows an "Ir al minuto" button).

**Done when:** staff get correct, cited Spanish answers and timestamp links work on desktop and iPhone.

## Deploying to AWS (suggested)

- **App Runner** (or ECS Fargate) for the API, from `coach-service/Dockerfile`.
- A second service/task running `python -m app.worker` with ffmpeg (same image).
- **RDS for PostgreSQL 16** with the `vector` extension (the first start runs migrations).
- Secrets in AWS Secrets Manager, passed as environment variables.
- Point the plugin's **Coach service URL** at the API and set `CORS_ORIGINS` to the academy domain.

## Open questions still to settle

Final plan names and limits · coach name/persona and tone · upgrade page URL
(filter `socio_coach_upgrade_url`, default `/planes/`) · real URLs/plans in `tools.yaml`.
