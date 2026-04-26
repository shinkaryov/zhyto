# ============================================================
# Terraform Azure Infrastructure Configuration
# Ukraine Invest Assistant - Main Configuration
# ============================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }

  backend "azurerm" {}
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
  tenant_id       = var.azure_tenant_id
}

data "azurerm_client_config" "current" {}

locals {
  storage_data_principal_object_ids = distinct(
    concat(
      [data.azurerm_client_config.current.object_id],
      var.extra_storage_data_principal_object_ids
    )
  )
}

# ============================================================
# Resource Group
# ============================================================

resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.azure_location

  tags = merge(
    var.common_tags,
    {
      Name        = "ukraine-invest-rg"
      Environment = var.environment
    }
  )
}

# ============================================================
# Container Registry (ACR)
# ============================================================

module "container_registry" {
  source = "./modules/container_registry"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  registry_name       = var.container_registry_name
  sku                 = var.acr_sku
  admin_enabled       = var.acr_admin_enabled

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-acr" }
  )
}

# ============================================================
# Azure Cosmos DB (Serverless)
# ============================================================

module "cosmos_db" {
  source = "./modules/cosmos_db"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  account_name        = var.cosmos_db_account_name
  environment         = var.environment

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-cosmosdb" }
  )
}

# ============================================================
# Azure Storage (artifacts + static frontend + Chroma share)
# ============================================================

module "storage" {
  source = "./modules/storage"

  resource_group_name   = azurerm_resource_group.main.name
  location              = azurerm_resource_group.main.location
  storage_account_name  = var.storage_account_name
  chroma_share_name     = var.chroma_share_name
  chroma_share_quota_gb = var.chroma_share_quota_gb
  environment           = var.environment

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-storage" }
  )
}

# Grant storage data-plane access to deployment principal (and optionally extra principals)
resource "azurerm_role_assignment" "storage_blob_data_contributor" {
  for_each = toset(local.storage_data_principal_object_ids)

  scope                = module.storage.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "storage_file_data_smb_share_contributor" {
  for_each = toset(local.storage_data_principal_object_ids)

  scope                = module.storage.storage_account_id
  role_definition_name = "Storage File Data SMB Share Contributor"
  principal_id         = each.value
}

# ============================================================
# Observability (Log Analytics + App diagnostics)
# ============================================================

resource "azurerm_log_analytics_workspace" "main" {
  name                = var.log_analytics_workspace_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_analytics_retention_days

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-log-analytics" }
  )
}

# ============================================================
# Azure OpenAI / Foundry OpenAI
# ============================================================

module "openai" {
  source = "./modules/openai"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  account_name                  = var.openai_account_name
  custom_subdomain_name         = var.openai_custom_subdomain_name
  account_sku_name              = var.openai_account_sku_name
  public_network_access_enabled = var.openai_public_network_access_enabled

  default_deployment_name         = var.openai_default_deployment_name
  default_model_name              = var.openai_default_model_name
  default_model_version           = var.openai_default_model_version
  default_deployment_sku_name     = var.openai_default_deployment_sku_name
  default_deployment_sku_capacity = var.openai_default_deployment_sku_capacity

  enable_advanced_deployment       = var.openai_enable_advanced_deployment
  advanced_deployment_name         = var.openai_advanced_deployment_name
  advanced_model_name              = var.openai_advanced_model_name
  advanced_model_version           = var.openai_advanced_model_version
  advanced_deployment_sku_name     = var.openai_advanced_deployment_sku_name
  advanced_deployment_sku_capacity = var.openai_advanced_deployment_sku_capacity

  embedding_deployment_name         = var.openai_embedding_deployment_name
  embedding_model_name              = var.openai_embedding_model_name
  embedding_model_version           = var.openai_embedding_model_version
  embedding_deployment_sku_name     = var.openai_embedding_deployment_sku_name
  embedding_deployment_sku_capacity = var.openai_embedding_deployment_sku_capacity
  rai_policy_name                   = var.openai_rai_policy_name

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-openai" }
  )
}

# ============================================================
# Azure Key Vault (for secrets)
# ============================================================

module "keyvault" {
  source = "./modules/keyvault"

  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  keyvault_name       = var.keyvault_name
  tenant_id           = var.azure_tenant_id
  environment         = var.environment

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-keyvault" }
  )
}

resource "azurerm_key_vault_secret" "openai_api_key" {
  name         = "azure-openai-api-key"
  value        = module.openai.primary_access_key
  key_vault_id = module.keyvault.keyvault_id

  depends_on = [module.keyvault]
}

resource "azurerm_key_vault_secret" "cosmos_connection_string" {
  name         = "cosmos-db-connection-string"
  value        = module.cosmos_db.connection_string
  key_vault_id = module.keyvault.keyvault_id

  depends_on = [module.keyvault]
}

# ============================================================
# Backend Web App (FastAPI container)
# ============================================================

module "web_app" {
  source = "./modules/web_app"

  resource_group_name    = azurerm_resource_group.main.name
  location               = azurerm_resource_group.main.location
  app_service_plan_name  = var.app_service_plan_name
  app_service_plan_sku   = var.app_service_plan_sku
  web_app_name           = var.web_app_name
  container_registry_url = module.container_registry.login_server
  container_registry_id  = module.container_registry.registry_id
  container_image_name   = var.container_image_name
  container_image_tag    = var.container_image_tag
  environment            = var.environment

  health_check_path = var.backend_health_check_path
  always_on         = var.backend_always_on

  storage_mounts = [
    {
      name         = "chroma"
      type         = "AzureFiles"
      account_name = module.storage.storage_account_name
      share_name   = module.storage.chroma_share_name
      access_key   = module.storage.primary_access_key
      mount_path   = var.chroma_mount_path
    }
  ]

  app_settings = {
    "ENVIRONMENT"                            = "production"
    "APP_ENV"                                = "production"
    "APP_DEBUG"                              = "false"
    "LOG_LEVEL"                              = "INFO"
    "USE_MOCK_OPENAI"                        = "false"
    "USE_MOCK_COSMOS"                        = "false"
    "USE_MOCK_AUTH"                          = "false"
    "FEATURE_AZURE_OPENAI_ENABLED"           = "true"
    "FEATURE_COSMOS_DB_ENABLED"              = "true"
    "FAIL_OPEN_TO_MOCK_IN_PRODUCTION"        = "false"
    "AZURE_OPENAI_ENDPOINT"                  = module.openai.endpoint
    "AZURE_OPENAI_API_KEY"                   = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.openai_api_key})"
    "AZURE_OPENAI_DEPLOYMENT_NAME"           = module.openai.default_deployment_name
    "AZURE_OPENAI_DEFAULT_DEPLOYMENT"        = module.openai.default_deployment_name
    "AZURE_OPENAI_ADVANCED_DEPLOYMENT"       = module.openai.advanced_deployment_name
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME" = module.openai.embedding_deployment_name
    "COSMOS_DB_CONNECTION_STRING"            = "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.cosmos_connection_string})"
    "CHROMA_DB_PATH"                         = var.chroma_mount_path
    "CHROMA_PERSIST_DIR"                     = var.chroma_mount_path
    "ENTRA_REDIRECT_URI"                     = var.entra_redirect_uri
    "AUTH_TOKEN_SECRET"                      = var.auth_token_secret
    "WEBSITE_WARMUP_PATH"                    = var.backend_health_check_path
    "WEBSITE_WARMUP_STATUSES"                = "200"
    "WEBSITES_CONTAINER_START_TIME_LIMIT"    = "600"
  }

  tags = merge(
    var.common_tags,
    { Name = "ukraine-invest-backend-webapp" }
  )

  depends_on = [
    module.container_registry,
    module.cosmos_db,
    module.storage,
    module.openai,
    module.keyvault,
    azurerm_key_vault_secret.openai_api_key,
    azurerm_key_vault_secret.cosmos_connection_string,
  ]
}

resource "azurerm_key_vault_access_policy" "webapp_secrets_reader" {
  key_vault_id = module.keyvault.keyvault_id
  tenant_id    = var.azure_tenant_id
  object_id    = module.web_app.principal_id

  secret_permissions = ["Get", "List"]
}

resource "azurerm_monitor_diagnostic_setting" "web_app" {
  name                       = "diag-webapp-${var.environment}"
  target_resource_id         = module.web_app.web_app_id
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  enabled_log {
    category_group = "allLogs"
  }

  metric {
    category = "AllMetrics"
    enabled  = true
  }
}
