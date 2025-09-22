# Zorgwaard Knowledge Base

Streamlit app for managing and querying Zorgwaard knowledge backed by PostgreSQL + pgvector.

## Prerequisites

- Docker & Docker Compose
- OpenAI API key (for embeddings and chat completions)

## Quick Start

1. Copy the example environment file and fill in secrets:
   ```bash
   cp .env.example .env
   ```
   Update `OPENAI_API_KEY`. The `DATABASE_URL` already targets the database exposed by the compose stack.

2. Build and start the stack:
   ```bash
   docker compose up --build
   ```

   This launches:
   - `db`: PostgreSQL with the `pgvector` extension
   - `app`: Streamlit frontend served on [http://localhost:8501](http://localhost:8501)

3. Stop the stack:
   ```bash
   docker compose down
   ```

   Database data persists in the `postgres_data` Docker volume.

## Local Development Notes

- The app container mounts the project directory, so code changes refresh automatically.
- The schema is created at runtime; no manual migrations required yet.
- To access the database directly:
  ```bash
  docker compose exec db psql -U zorgwaard -d zorgwaard
  ```

## Environment Variables

| Variable          | Description                             |
|-------------------|-----------------------------------------|
| `OPENAI_API_KEY`  | OpenAI credentials for embeddings/LLM    |
| `DATABASE_URL`    | Postgres connection string               |
| `STREAMLIT_SERVER_PORT` | Optional Streamlit port override |

## Tests / Tooling

Python dependencies are managed via `requirements.txt`. You can run commands inside the app container, e.g.:
```bash
docker compose exec app bash
```
