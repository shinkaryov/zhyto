output "account_id" {
  description = "ID of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.main.id
}

output "account_name" {
  description = "Name of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.main.name
}

output "endpoint" {
  description = "Endpoint of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.main.endpoint
}

output "primary_key" {
  description = "Primary key of the Cosmos DB account"
  value       = azurerm_cosmosdb_account.main.primary_key
  sensitive   = true
}

output "connection_string" {
  description = "Connection string for Cosmos DB"
  value       = "DefaultEndpointsProtocol=https;AccountName=${azurerm_cosmosdb_account.main.name};AccountKey=${azurerm_cosmosdb_account.main.primary_key};EndpointSuffix=documents.azure.com"
  sensitive   = true
}

