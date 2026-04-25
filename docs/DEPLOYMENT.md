# Deployment

## Deployment Model

Cloud deploy is manual-only via GitHub Actions `workflow_dispatch`.

Workflows:
- [`infra-deploy.yml`](/Users/admin/PycharmProjects/PythonProject18 копія/.github/workflows/infra-deploy.yml)
- [`app-deploy.yml`](/Users/admin/PycharmProjects/PythonProject18 копія/.github/workflows/app-deploy.yml)
- [`data-restore.yml`](/Users/admin/PycharmProjects/PythonProject18 копія/.github/workflows/data-restore.yml)
- optional bootstrap state: [`terraform-bootstrap-state.yml`](/Users/admin/PycharmProjects/PythonProject18 копія/.github/workflows/terraform-bootstrap-state.yml)

## Order of Operations

1. Bootstrap Terraform state storage (once per environment).
2. Run **Infra Deploy** (`plan` then `apply`).
3. Run **Data Restore** to restore Chroma snapshot (and optionally upload raw JSON artifacts).
4. Run **App Deploy** to deploy backend image and frontend static build.

## Required GitHub Secrets

Core Azure:
- `AZURE_CREDENTIALS`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_TENANT_ID`
- `AZURE_RESOURCE_GROUP`

Terraform backend state:
- `TFSTATE_RESOURCE_GROUP`
- `TFSTATE_STORAGE_ACCOUNT`
- `TFSTATE_CONTAINER`
- `TFSTATE_KEY`

Infra naming/config:
- `ACR_NAME`
- `BACKEND_WEB_APP_NAME`
- `COSMOS_DB_ACCOUNT_NAME`
- `KEYVAULT_NAME`
- `STORAGE_ACCOUNT_NAME`
- `OPENAI_ACCOUNT_NAME`
- `OPENAI_CUSTOM_SUBDOMAIN_NAME`
- `AUTH_TOKEN_SECRET`
- `AUTH_WHITELIST_BLOB_NAME` (optional, defaults to `email_whitelist.txt`)

Data restore:
- `CHROMA_SHARE_NAME`

Optional frontend override:
- `FRONTEND_API_BASE_URL`

## Permissions Needed for CI Identity

Service principal used by `AZURE_CREDENTIALS` should be able to:
- Deploy ARM resources in target resource group
- Push/pull ACR images
- Update Web App configuration
- Read/write Blob and File data in storage account (for static site + snapshots)

## Chroma Snapshot Restore

`data-restore.yml` workflow performs:
- Download snapshot from `chroma-snapshots` container
- Extract archive (`.tar.gz` or `.zip`)
- Upload extracted files to Azure Files share used by backend mount
- Restart backend web app

No data ingestion/embedding is run.

## Auth Whitelist Artifact

`app-deploy.yml` downloads `src/auth/email_whitelist.txt` from Blob container `raw-data` before backend image build.

Default blob name is `email_whitelist.txt`, or override with `AUTH_WHITELIST_BLOB_NAME`.

## Rollback Basics

- Backend rollback: rerun `app-deploy.yml` with prior `image_tag`.
- Frontend rollback: redeploy previous frontend build artifacts to `$web`.
- Chroma rollback: rerun `data-restore.yml` with prior snapshot blob.
- Infra rollback: use Terraform in controlled `plan`/`apply` cycle.

## Health Verification

After backend deploy:
- `https://<backend-web-app>.azurewebsites.net/health` should return `200`.

After frontend deploy:
- Storage static website endpoint should serve `index.html`.

## Notes

- Region target is Poland Central.
- Cosmos is serverless.
- Azure OpenAI is Terraform-provisioned with deployment names consumed by backend config.
- Local mode remains separate via Docker Compose.
