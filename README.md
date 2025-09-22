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

## Deploying to Railway

1. Install the Railway CLI and log in (`npm i -g railway && railway login`).
2. Run `railway up` from the project root. The bundled `railway.json` provisions a serverless Streamlit service and a managed Postgres database (with the `DATABASE_URL` variable wired in automatically).
3. Set the required secrets, for example:
   ```bash
   railway variables set OPENAI_API_KEY=sk-...
   ```
4. Deploy with `railway deploy`. In the Railway dashboard, open the `zorgwaard-kb` service settings and enable sleep/scale-to-zero (min replicas `0`, max `1`) so the app powers down when idle.

The service exposes Streamlit on `/_stcore/health` for health checks, which Railway uses to determine readiness.

## Tests / Tooling

Python dependencies are managed via `requirements.txt`. You can run commands inside the app container, e.g.:
```bash
docker compose exec app bash
```
