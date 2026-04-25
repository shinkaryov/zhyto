# Data Artifacts

## Purpose

Define how non-runtime data is handled across local and cloud modes.

## Artifact Classes

### 1) Raw Source JSON (canonical)
Location:
- Local-only working files under `src/invest_app_data/` (JSON files are git-ignored)

Cloud storage:
- Blob container: `raw-data/`

Usage:
- Canonical source artifacts and offline processing inputs.
- Not required at backend runtime for normal cloud serving.

### 2) Chroma Vector Snapshot (runtime data artifact)
Location:
- Local-only working files under `chroma_data/` (git-ignored)

Cloud storage:
- Blob container: `chroma-snapshots/`
- Runtime mount target: Azure Files share mounted into backend container path (`CHROMA_DB_PATH` / `CHROMA_PERSIST_DIR`)

Usage:
- Restore/pull prebuilt vectors.
- Reuse vectors; do **not** re-embed on deploy/startup.
- Store versioned snapshots in Blob and restore to cloud runtime mount.

Recommended snapshot naming:
- `chroma-<env>-<yyyymmdd>-v<revision>.tar.gz`

### 3) Local Cosmos Mock
Location:
- [`local_cosmos_db.json/mock_cosmos_db.json`](/Users/admin/PycharmProjects/PythonProject18 копія/local_cosmos_db.json/mock_cosmos_db.json)

Usage:
- Local dev/testing only.

Rules:
- Never upload to cloud.
- Never include in production image.

### 4) Auth Email Whitelist
Location:
- Local-only `src/auth/email_whitelist.txt` (git-ignored)

Cloud storage:
- Blob container: `raw-data/`
- Blob name: `email_whitelist.txt` (or value of `AUTH_WHITELIST_BLOB_NAME`)

Usage:
- Downloaded by `app-deploy.yml` before backend image build.
- Keeps access-control list out of Git while preserving deterministic deploys.

### 5) Offline Ingestion Tool
Location:
- [`src/rag/data_ingestion.py`](/Users/admin/PycharmProjects/PythonProject18 копія/src/rag/data_ingestion.py)

Usage:
- Manual offline ingestion only.
- Not part of deploy workflows.
- Not part of app startup.

## Image Packaging Rules

Production images should not include:
- `chroma_data/`
- `local_cosmos_db.json/`
- raw JSON ingestion artifacts unless explicitly required

`.dockerignore` enforces this.

## Restore Flow Summary

Manual workflow `data-restore.yml`:
1. Download selected Chroma snapshot from `chroma-snapshots`.
2. Extract archive.
3. Upload extracted content to Azure Files share used by backend mount.
4. Restart backend.

No embedding jobs are triggered.
