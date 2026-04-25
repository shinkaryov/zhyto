# ============================================================
# Azure Web App for Containers Module
# ============================================================

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_service_plan" "main" {
  name                = var.app_service_plan_name
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = var.app_service_plan_sku

  tags = var.tags
}

resource "azurerm_linux_web_app" "main" {
  name                = var.web_app_name
  location            = var.location
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.main.id

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on                               = var.always_on
    container_registry_use_managed_identity = true

    application_stack {
      docker_image_name   = "${var.container_registry_url}/${var.container_image_name}:${var.container_image_tag}"
      docker_registry_url = "https://${var.container_registry_url}"
    }

    health_check_path = var.health_check_path

    http2_enabled = true
  }

  dynamic "storage_account" {
    for_each = var.storage_mounts
    content {
      name         = storage_account.value.name
      type         = storage_account.value.type
      account_name = storage_account.value.account_name
      share_name   = storage_account.value.share_name
      access_key   = storage_account.value.access_key
      mount_path   = storage_account.value.mount_path
    }
  }

  app_settings = merge(
    var.app_settings,
    {
      "DOCKER_REGISTRY_SERVER_URL"          = "https://${var.container_registry_url}"
      "DOCKER_REGISTRY_SERVER_USERNAME"     = ""
      "DOCKER_REGISTRY_SERVER_PASSWORD"     = ""
      "WEBSITES_ENABLE_APP_SERVICE_STORAGE" = var.enable_app_service_storage ? "true" : "false"
    }
  )

  logs {
    http_logs {
      file_system {
        retention_in_days = 7
        retention_in_mb   = 35
      }
    }
  }

  tags = var.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_linux_web_app.main.identity[0].principal_id
}
