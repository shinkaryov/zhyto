# Local Development

## Goal

Run the full app locally without requiring cloud resources.

## Start

```bash
docker compose up --build
```

Services:
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- Backend health: `http://localhost:8000/health`

## Local Data Behavior

- Chroma uses local persistent path (`CHROMA_DB_PATH`, default `./chroma_data`).
- Cosmos can run in local JSON mock mode (`USE_MOCK_COSMOS=true`).
- `local_cosmos_db.json` is local-only dev data and must not be used in cloud deploy.

## Environment

Use `.env` derived from [`.env.example`](https://github.com/shinkaryov/zhyto/blob/master/.env.example).

Typical local-safe flags:
- `USE_MOCK_AUTH=true`
- `USE_MOCK_COSMOS=true`
- `USE_MOCK_OPENAI=true` (or set real Azure OpenAI values explicitly)

Auth whitelist:
- Keep local file at `src/auth/email_whitelist.txt` (git-ignored).
- Use [`src/auth/email_whitelist.example.txt`](https://github.com/shinkaryov/zhyto/blob/master/src/auth/email_whitelist.example.txt) as a template.

## Chroma Notes

The production deployment reuses prebuilt vectors via snapshot restore.

Local mode can reuse the same local `chroma_data` directory. Re-embedding is optional/manual and **not** part of normal startup.

## Optional Manual Ingestion (Local Only)

[`src/rag/data_ingestion.py`](https://github.com/shinkaryov/zhyto/blob/master/src/rag/data_ingestion.py) remains an offline tool. Do not run it as part of app startup/deploy scripts.
When you need it, install ingestion-only deps:

```bash
pip install -r backend/requirements-ingestion.txt
```
