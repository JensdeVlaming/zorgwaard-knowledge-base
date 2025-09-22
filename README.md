# Zorgwaard Knowledge Base

Streamlit application that lets Zorgwaard teams capture knowledge, enrich it with embeddings, and answer free-form questions using retrieval-augmented generation (RAG). The stack combines PostgreSQL + pgvector for storage, SQLAlchemy for the ORM layer, and OpenAI models for embeddings and answering.

## Features
- **Note management:** create, list, and curate knowledge notes with metadata, entities, and tags.
- **Semantic search:** generate embeddings with OpenAI and search notes by similarity and entity filters.
- **LLM answering:** answer Dutch questions with contextual citations using a retrieval-augmented pipeline.
- **Plain SQL migrations:** database schema lives in `infrastructure/migrations/sql` and is applied automatically on startup.
- **Railway-ready:** one-click deployment with managed Postgres, health checks, and scale-to-zero defaults.

## Architecture
- **Frontend:** Streamlit (`app.py` + components in `ui/`).
- **Backend services:** SQLAlchemy models (`models/`), service layer (`services/`), and LLM helpers (`infrastructure/llm/`).
- **Database:** PostgreSQL with the pgvector extension, managed through plain-SQL migrations.
- **Integrations:** OpenAI (embeddings + chat completions) configured via `core/openai_client.py`.

## Prerequisites
- Docker & Docker Compose (recommended for local development)
- Python 3.11+ if running without Docker
- An OpenAI API key

## Getting Started (Docker)
1. Copy the example environment file and fill in your secrets:
   ```bash
   cp .env.example .env
   # edit .env to set OPENAI_API_KEY, DB_USER, PGPASSWORD, and any overrides you need
   ```
2. Start the stack:
   ```bash
   docker compose up --build
   ```
   Services launched:
   - `db`: PostgreSQL + pgvector, exposed on `localhost:$DB_PORT`, default `5432`
   - `app`: Streamlit UI, exposed on `localhost:$STREAMLIT_SERVER_PORT`, default `8501`

3. Stop everything:
   ```bash
   docker compose down
   ```
   Database data persists inside the `postgres_data` Docker volume.

## Database Migrations
- Plain SQL migration files live in `infrastructure/migrations/sql`. Filenames should be ordered (e.g. `0002_add_x.sql`).
- The migration runner (`infrastructure/migrations/runner.py`) keeps a `schema_migrations` ledger and executes new files on startup.
- Streamlit triggers migrations once per process via `core/db_client.init_db()`; containers (Docker, Railway) also run `python -m infrastructure.railway.bootstrap` before serving requests.
- To apply migrations manually:
  ```bash
  python -m infrastructure.railway.bootstrap
  ```

> **Note:** pgvector indexes such as `ivfflat`/`hnsw` are omitted because Railway's current pgvector build caps dimensions at 2 000; embeddings here are 3 072 dimensions.

## Environment Variables
| Variable | Description |
| --- | --- |
| `OPENAI_API_KEY` | Required. OpenAI key used for embeddings and chat completions |
| `DB_USER` | Required. PostgreSQL username used by the app (no default) |
| `PGPASSWORD` | Required. Password for `DB_USER` |
| `DB_NAME` | Optional. Database name used in the connection; defaults to `knowledge_base` |
| `DB_HOST` | Optional. PostgreSQL host; defaults to `localhost` |
| `DB_PORT` | Optional. PostgreSQL port; defaults to `5432` |
| `EMBED_MODEL` | Optional. OpenAI embedding model; defaults to `text-embedding-3-large` |
| `CHAT_MODEL` | Optional. Chat completion model; defaults to `gpt-4o-mini` |
| `STREAMLIT_SERVER_PORT` | Optional. Host-facing Streamlit port; defaults to `8501` |
| `STREAMLIT_SERVER_FILE_WATCHER_TYPE` | Optional. Defaults to `poll` for Docker volume compatibility |

## Local Tooling
- `make reset-db` – drop and recreate the database schema using the migrations.
- `make psql` – open a psql shell using Makefile defaults or values from your `.env`.

## Disclaimer
See [DISCLAIMER.md](DISCLAIMER.md) for important limitations of use.

## License
Released under the MIT License. See `LICENSE` for details.
