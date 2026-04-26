# ============================================================
# Terraform Variables
# Ukraine Invest Assistant
# ============================================================

variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "azure_tenant_id" {
  description = "Azure tenant ID"
  type        = string
  sensitive   = true
}

variable "azure_location" {
  description = "Azure region for resources"
  type        = string
  default     = "polandcentral"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be 'dev', 'staging', or 'prod'."
  }
}

# ============================================================
# Resource Group
# ============================================================

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-zhyto-ukrinvest"
}

# ============================================================
# Container Registry (ACR)
# ============================================================

variable "container_registry_name" {
  description = "Name of the container registry (must be globally unique)"
  type        = string
  default     = "acrzhytoukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9]+$", var.container_registry_name))
    error_message = "Container registry name must contain only lowercase letters and numbers."
  }
}

variable "acr_sku" {
  description = "SKU for Azure Container Registry"
  type        = string
  default     = "Basic"
  validation {
    condition     = contains(["Basic", "Standard", "Premium"], var.acr_sku)
    error_message = "ACR SKU must be Basic, Standard, or Premium."
  }
}

variable "acr_admin_enabled" {
  description = "Whether to enable admin user for ACR"
  type        = bool
  default     = false
}

# ============================================================
# Backend Web App for Containers
# ============================================================

variable "web_app_name" {
  description = "Name of the backend web app (must be globally unique)"
  type        = string
  default     = "app-zhyto-ukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.web_app_name))
    error_message = "Web app name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "app_service_plan_name" {
  description = "Name of the app service plan"
  type        = string
  default     = "asp-zhyto-ukrinvest"
}

variable "app_service_plan_sku" {
  description = "SKU for app service plan"
  type        = string
  default     = "B1"
}

variable "container_image_name" {
  description = "Name of the backend container image"
  type        = string
  default     = "ukraine-invest-backend"
}

variable "container_image_tag" {
  description = "Tag for the backend container image"
  type        = string
  default     = "latest"
}

variable "backend_health_check_path" {
  description = "Health check path for backend app"
  type        = string
  default     = "/health/ready"
}

variable "backend_always_on" {
  description = "Enable always-on for backend app service"
  type        = bool
  default     = true
}

variable "chroma_mount_path" {
  description = "Path in backend container where Chroma Azure File Share is mounted"
  type        = string
  default     = "/mounts/chroma"
}

# ============================================================
# Cosmos DB
# ============================================================

variable "cosmos_db_account_name" {
  description = "Name of the Cosmos DB account (must be globally unique)"
  type        = string
  default     = "cosmos-zhyto-ukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.cosmos_db_account_name))
    error_message = "Cosmos DB account name must contain only lowercase letters, numbers, and hyphens."
  }
}

# ============================================================
# Key Vault
# ============================================================

variable "keyvault_name" {
  description = "Name of the Key Vault (must be globally unique)"
  type        = string
  default     = "kv-zhyto-ukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.keyvault_name))
    error_message = "Key Vault name must contain only lowercase letters, numbers, and hyphens."
  }
}

# ============================================================
# Azure OpenAI / Foundry OpenAI
# ============================================================

variable "openai_account_name" {
  description = "Azure OpenAI account name (must be globally unique)"
  type        = string
  default     = "oaizhytoukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.openai_account_name))
    error_message = "OpenAI account name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "openai_custom_subdomain_name" {
  description = "Azure OpenAI custom subdomain used by SDK endpoint"
  type        = string
  default     = "oaizhytoukrinvest"
}

variable "openai_account_sku_name" {
  description = "Azure OpenAI account SKU"
  type        = string
  default     = "S0"
}

variable "openai_public_network_access_enabled" {
  description = "Whether public network access is enabled for Azure OpenAI"
  type        = bool
  default     = true
}

variable "openai_default_deployment_name" {
  description = "Default chat deployment name"
  type        = string
  default     = "gpt-5-4-mini"
}

variable "openai_default_model_name" {
  description = "Default chat model name"
  type        = string
  default     = "gpt-5.4-mini"
}

variable "openai_default_model_version" {
  description = "Default chat model version"
  type        = string
  default     = "2026-03-17"
}

variable "openai_default_deployment_sku_name" {
  description = "Default chat deployment SKU name"
  type        = string
  default     = "GlobalStandard"
}

variable "openai_default_deployment_sku_capacity" {
  description = "Default chat deployment SKU capacity"
  type        = number
  default     = 1
}

variable "openai_enable_advanced_deployment" {
  description = "Whether to create advanced deployment"
  type        = bool
  default     = true
}

variable "openai_advanced_deployment_name" {
  description = "Advanced chat deployment name"
  type        = string
  default     = "gpt-5-4-advanced"
}

variable "openai_advanced_model_name" {
  description = "Advanced chat model name"
  type        = string
  default     = "gpt-5.4"
}

variable "openai_advanced_model_version" {
  description = "Advanced chat model version"
  type        = string
  default     = "2026-03-05"
}

variable "openai_advanced_deployment_sku_name" {
  description = "Advanced chat deployment SKU name"
  type        = string
  default     = "GlobalStandard"
}

variable "openai_advanced_deployment_sku_capacity" {
  description = "Advanced chat deployment SKU capacity"
  type        = number
  default     = 1
}

variable "openai_embedding_deployment_name" {
  description = "Embedding deployment name"
  type        = string
  default     = "text-embedding-3-small"
}

variable "openai_embedding_model_name" {
  description = "Embedding model name"
  type        = string
  default     = "text-embedding-3-small"
}

variable "openai_embedding_model_version" {
  description = "Embedding model version"
  type        = string
  default     = "1"
}

variable "openai_embedding_deployment_sku_name" {
  description = "Embedding deployment SKU name"
  type        = string
  default     = "GlobalStandard"
}

variable "openai_embedding_deployment_sku_capacity" {
  description = "Embedding deployment SKU capacity"
  type        = number
  default     = 1
}

# ============================================================
# Storage Account
# ============================================================

variable "storage_account_name" {
  description = "Name of the storage account (must be globally unique, lowercase alnum)"
  type        = string
  default     = "sazhytoukrinvest"
  validation {
    condition     = can(regex("^[a-z0-9]+$", var.storage_account_name))
    error_message = "Storage account name must contain only lowercase letters and numbers."
  }
}

variable "chroma_share_name" {
  description = "Azure Files share name for persistent Chroma index"
  type        = string
  default     = "chroma-zhyto-ukrinvest"
}

variable "chroma_share_quota_gb" {
  description = "Azure Files share quota in GB for Chroma persistence"
  type        = number
  default     = 100
}

variable "log_analytics_workspace_name" {
  description = "Log Analytics workspace name for centralized app logs"
  type        = string
  default     = "log-zhyto-ukrinvest"
}

variable "log_analytics_retention_days" {
  description = "Retention in days for Log Analytics workspace data"
  type        = number
  default     = 30
}

variable "extra_storage_data_principal_object_ids" {
  description = "Optional additional Entra object IDs to grant Blob/File data access on storage account"
  type        = list(string)
  default     = []
}

# ============================================================
# App Settings / Auth
# ============================================================

variable "entra_redirect_uri" {
  description = "Redirect URI used by Entra login flow"
  type        = string
  default     = "http://localhost:3000"
}

variable "auth_token_secret" {
  description = "JWT/auth token secret for backend auth"
  type        = string
  sensitive   = true
}

# ============================================================
# Common Tags
# ============================================================

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "UkraineInvest"
    ManagedBy   = "Terraform"
    CreatedDate = "2026"
  }
}
