output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.main.id
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.main.name
}

output "primary_blob_endpoint" {
  description = "The blob endpoint URL"
  value       = azurerm_storage_account.main.primary_blob_endpoint
}

output "primary_web_host" {
  description = "Static website hostname"
  value       = azurerm_storage_account.main.primary_web_host
}

output "primary_web_endpoint" {
  description = "Static website endpoint URL"
  value       = azurerm_storage_account.main.primary_web_endpoint
}

output "primary_access_key" {
  description = "Primary access key for storage account"
  value       = azurerm_storage_account.main.primary_access_key
  sensitive   = true
}

output "chroma_share_name" {
  description = "Azure Files share used for Chroma persistence"
  value       = azurerm_storage_share.chroma.name
}

output "raw_data_container_name" {
  description = "Container for canonical raw JSON artifacts"
  value       = azurerm_storage_container.raw_data.name
}

output "chroma_snapshots_container_name" {
  description = "Container for compressed Chroma snapshots"
  value       = azurerm_storage_container.chroma_snapshots.name
}

output "backups_container_name" {
  description = "Container for operational backups"
  value       = azurerm_storage_container.backups.name
}
