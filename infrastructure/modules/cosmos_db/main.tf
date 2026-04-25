# ============================================================
# Azure Cosmos DB Module (Serverless Mode for MVP)
# ============================================================

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_cosmosdb_account" "main" {
  name                = var.account_name
  location            = var.location
  resource_group_name = var.resource_group_name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  # Вмикаємо режим Serverless
  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level       = "Session"
    max_interval_in_seconds = 5
    max_staleness_prefix    = 100
  }

  geo_location {
    location          = var.location
    failover_priority = 0
  }

  tags = var.tags
}

# Створюємо базу (без throughput)
resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "ukraine_invest_db"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
}

# Створюємо контейнери (видаляємо throughput з усіх)
resource "azurerm_cosmosdb_sql_container" "users" {
  name                = "users"
  database_name       = azurerm_cosmosdb_sql_database.main.name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  partition_key_paths = ["/id"]

  indexing_policy {
    indexing_mode = "consistent"
  }
}

resource "azurerm_cosmosdb_sql_container" "user_notes" {
  name                = "user_notes"
  database_name       = azurerm_cosmosdb_sql_database.main.name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  partition_key_paths = ["/user_id"]

  indexing_policy {
    indexing_mode = "consistent"
  }
}

resource "azurerm_cosmosdb_sql_container" "portfolio_assets" {
  name                = "portfolio_assets"
  database_name       = azurerm_cosmosdb_sql_database.main.name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  partition_key_paths = ["/user_id"]

  indexing_policy {
    indexing_mode = "consistent"
  }
}

resource "azurerm_cosmosdb_sql_container" "chat_history" {
  name                = "chat_history"
  database_name       = azurerm_cosmosdb_sql_database.main.name
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  partition_key_paths = ["/user_id"]

  indexing_policy {
    indexing_mode = "consistent"
  }
}
