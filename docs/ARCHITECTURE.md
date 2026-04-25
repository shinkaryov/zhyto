# Architecture

## Supported Modes

This repository supports exactly two runtime/deployment modes:

1. **Cloud mode**: manual GitHub Actions `workflow_dispatch` only
2. **Local mode**: `docker compose up --build`

No push-based auto-deploy is supported.

## Local Architecture (Docker Compose)

```text
React (Vite dev/prod container) -> FastAPI backend -> local Chroma path (PersistentClient)
                                         |
                                         +-> local JSON Cosmos mock OR Azure Cosmos (if configured)
```

Local services come from [`docker-compose.yml`](/Users/admin/PycharmProjects/PythonProject18 копія/docker-compose.yml):
- `frontend`
- `backend`

Backend retrieval logic uses local persistent Chroma path by default via [`src/db/chroma_client.py`](/Users/admin/PycharmProjects/PythonProject18 копія/src/db/chroma_client.py).

## Cloud Architecture (Low-Cost / Poland Central)

```text
React static build ($web in Azure Storage static website)
        |
        v
FastAPI backend (Azure Linux Web App for Containers)
        |
        +-> Azure Cosmos DB (serverless, single region)
        +-> Azure OpenAI (Terraform provisioned account + deployments)
        +-> Chroma PersistentClient path mounted from Azure Files share

Artifact storage:
- raw-data/ (JSON source artifacts)
- chroma-snapshots/ (prebuilt vector snapshots)
- backups/
```

Infrastructure is managed by Terraform in [`infrastructure/`](/Users/admin/PycharmProjects/PythonProject18 копія/infrastructure).

## Cloud Components

- Resource Group (Poland Central)
- Azure Container Registry (backend image)
- Azure Linux Web App for Containers (backend)
- Azure Storage Account
  - Static website for frontend
  - Blob containers: `raw-data`, `chroma-snapshots`, `backups`
  - Azure Files share for Chroma mount
- Azure Cosmos DB (serverless)
- Azure OpenAI / Foundry OpenAI account + deployments
- Key Vault (secret storage / references)
- Managed Identity + AcrPull + Key Vault secret read permissions

## Chroma Strategy (No Re-Embedding)

Production does **not** run ingestion during deploy/startup.

- Backend uses `PersistentClient(path=CHROMA_DB_PATH)`.
- `CHROMA_DB_PATH` (or alias `CHROMA_PERSIST_DIR`) points to mounted Azure Files share path.
- Existing prebuilt Chroma snapshot is restored into that path by manual workflow.
- Existing vectors are reused directly.

This keeps runtime simple and cheap for low traffic.

## Cosmos Strategy

- Cosmos stays **serverless** by design.
- Single region deployment in Poland Central.
- No provisioned RU/autoscale mode.

## Caching Strategy

For expected load (<=5 concurrent, <=20/day):
- Keep existing in-process TTL caches in backend.
- No Redis by default.
- Static frontend assets served from Storage static website.

Rationale: lowest operational/cost overhead for current load.

## What Is Intentionally Not Included

- No auto-deploy on push.
- No mandatory Redis layer.
- No separate production Chroma server required.
- No embedding/data ingestion in runtime deploy path.
