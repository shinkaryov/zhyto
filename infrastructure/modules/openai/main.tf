# ============================================================
# Azure OpenAI / Foundry OpenAI Module
# ============================================================

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_cognitive_account" "openai" {
  name                = var.account_name
  location            = var.location
  resource_group_name = var.resource_group_name
  kind                = "OpenAI"
  sku_name            = var.account_sku_name

  custom_subdomain_name = var.custom_subdomain_name

  public_network_access_enabled = var.public_network_access_enabled

  tags = var.tags
}

resource "azurerm_cognitive_deployment" "default" {
  name                 = var.default_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.default_model_name
    version = var.default_model_version
  }

  scale {
    type     = var.default_deployment_sku_name
    capacity = var.default_deployment_sku_capacity
  }
}

resource "azurerm_cognitive_deployment" "advanced" {
  count                = var.enable_advanced_deployment ? 1 : 0
  name                 = var.advanced_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.advanced_model_name
    version = var.advanced_model_version
  }

  scale {
    type     = var.advanced_deployment_sku_name
    capacity = var.advanced_deployment_sku_capacity
  }
}

resource "azurerm_cognitive_deployment" "embedding" {
  name                 = var.embedding_deployment_name
  cognitive_account_id = azurerm_cognitive_account.openai.id

  model {
    format  = "OpenAI"
    name    = var.embedding_model_name
    version = var.embedding_model_version
  }

  scale {
    type     = var.embedding_deployment_sku_name
    capacity = var.embedding_deployment_sku_capacity
  }
}
