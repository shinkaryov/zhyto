# Deployment

## Deployment Model

Cloud deploy is manual-only via GitHub Actions `workflow_dispatch`.

Workflows:
- [`infra-deploy.yml`](https://github.com/shinkaryov/zhyto/blob/master/.github/workflows/infra-deploy.yml)
- [`app-deploy.yml`](https://github.com/shinkaryov/zhyto/blob/master/.github/workflows/app-deploy.yml)
- [`data-restore.yml`](https://github.com/shinkaryov/zhyto/blob/master/.github/workflows/data-restore.yml)
- bootstrap state: [`terraform-bootstrap-state.yml`](https://github.com/shinkaryov/zhyto/blob/master/.github/workflows/terraform-bootstrap-state.yml)

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

Terraform backend state:
- `TFSTATE_RESOURCE_GROUP`
- `TFSTATE_STORAGE_ACCOUNT`
- `TFSTATE_CONTAINER`
- `TFSTATE_KEY`

App secret:
- `AUTH_TOKEN_SECRET`

## Non-Sensitive Naming In Code

Resource names and non-sensitive settings are defined directly in workflow/Terraform code:
- Resource Group: `rg-zhyto-ukrinvest`
- ACR: `acrzhytoukrinvest` (Azure naming constraint: no hyphens)
- Web App: `app-zhyto-ukrinvest`
- App Service Plan: `asp-zhyto-ukrinvest`
- Cosmos DB account: `cosmos-zhyto-ukrinvest`
- Key Vault: `kv-zhyto-ukrinvest`
- Storage Account: `sazhytoukrinvest` (Azure naming constraint: no hyphens)
- OpenAI account/subdomain: `oaizhytoukrinvest` (Azure naming constraint: no hyphens)
- Chroma file share: `chroma-zhyto-ukrinvest`

## Permissions Needed for CI Identity

Service principal used by `AZURE_CREDENTIALS` should be able to:
- Deploy ARM resources in target resource group
- Push/pull ACR images
- Update Web App configuration
- Read/write Blob and File data in storage account (for static site + snapshots)

Terraform now creates storage data-plane role assignments on the storage account for the identity running `terraform apply`:
- `Storage Blob Data Contributor`
- `Storage File Data SMB Share Contributor`

If you also want your personal Entra user to upload blobs/files locally with `--auth-mode login`, add your Entra object ID to `extra_storage_data_principal_object_ids` and re-apply infra.

In GitHub Actions `infra-deploy.yml`, you can pass this without code changes via workflow input:
- `extra_storage_data_principal_object_ids_json`
- Example: `["11111111-2222-3333-4444-555555555555"]`

## Chroma Snapshot Restore

`data-restore.yml` workflow performs:
- Download snapshot from `chroma-snapshots` container
- Extract archive (`.tar.gz` or `.zip`)
- Upload extracted files to Azure Files share used by backend mount
- Restart backend web app

No data ingestion/embedding is run.

## Auth Whitelist Artifact

`app-deploy.yml` downloads `src/auth/email_whitelist.txt` from Blob container `raw-data` before backend image build.

Default blob name in workflow is `email_whitelist.txt`.

## Rollback Basics

- Backend rollback: rerun `app-deploy.yml` with prior `image_tag`.
- Frontend rollback: redeploy previous frontend build artifacts to `$web`.
- Chroma rollback: rerun `data-restore.yml` with prior snapshot blob.
- Infra rollback: use Terraform in controlled `plan`/`apply` cycle.

## Health Verification

After backend deploy:
- `https://<backend-web-app>.azurewebsites.net/health/ready` should return `200`.

After frontend deploy:
- Storage static website endpoint should serve `index.html`.

## Stability Notes

- App Service health check is configured to use `/health/ready` (dependency-aware readiness).
- Backend runs with `always_on=true` to reduce cold-start outages.
- Production is configured with `FAIL_OPEN_TO_MOCK_IN_PRODUCTION=false` to prevent silent fallback to local mock stores.
  - If Cosmos/Embeddings are unavailable, app reports not-ready/500 instead of writing to ephemeral mock files.

## Observability

Terraform provisions a Log Analytics workspace and diagnostic settings for backend Web App logs/metrics.

Where to check:
- Azure Portal -> Log Analytics workspaces -> `log-zhyto-ukrinvest` -> Logs.

Useful KQL starters:

```kusto
AppServiceConsoleLogs
| where _ResourceId has "app-zhyto-ukrinvest"
| where TimeGenerated > ago(2h)
| order by TimeGenerated desc
```

```kusto
AppServiceHTTPLogs
| where _ResourceId has "app-zhyto-ukrinvest"
| where ScStatus >= 500 or CsUriStem startswith "/health"
| where TimeGenerated > ago(24h)
| order by TimeGenerated desc
```

## Notes

- Region target is Poland Central.
- Cosmos is serverless.
- Azure OpenAI is Terraform-provisioned with deployment names consumed by backend config.
- Local mode remains separate via Docker Compose.
