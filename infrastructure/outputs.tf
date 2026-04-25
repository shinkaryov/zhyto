# ============================================================
# Terraform Outputs
# Ukraine Invest Assistant
# ============================================================

output "resource_group_id" {
  description = "ID of the resource group"
  value       = azurerm_resource_group.main.id
}

output "container_registry_id" {
  description = "ID of the container registry"
  value       = module.container_registry.registry_id
}

output "container_registry_login_server" {
  description = "Container registry login server URL"
  value       = module.container_registry.login_server
}

output "web_app_id" {
  description = "ID of the backend web app"
  value       = module.web_app.web_app_id
}

output "web_app_url" {
  description = "Default hostname URL of backend web app"
  value       = module.web_app.web_app_url
}

output "cosmos_db_account_id" {
  description = "ID of the Cosmos DB account"
  value       = module.cosmos_db.account_id
}

output "cosmos_db_endpoint" {
  description = "Cosmos DB endpoint URL"
  value       = module.cosmos_db.endpoint
}

output "keyvault_id" {
  description = "ID of the Key Vault"
  value       = module.keyvault.keyvault_id
}

output "storage_account_id" {
  description = "ID of the storage account"
  value       = module.storage.storage_account_id
}

output "storage_account_primary_blob_endpoint" {
  description = "The blob endpoint URL of the storage account"
  value       = module.storage.primary_blob_endpoint
}

output "frontend_static_website_url" {
  description = "Static website URL for React frontend"
  value       = module.storage.primary_web_endpoint
}

output "storage_raw_data_container" {
  description = "Blob container for raw JSON artifacts"
  value       = module.storage.raw_data_container_name
}

output "storage_chroma_snapshots_container" {
  description = "Blob container for Chroma snapshots"
  value       = module.storage.chroma_snapshots_container_name
}

output "storage_chroma_share" {
  description = "Azure Files share name for Chroma persistence"
  value       = module.storage.chroma_share_name
}

output "openai_account_id" {
  description = "Azure OpenAI account ID"
  value       = module.openai.account_id
}

output "openai_endpoint" {
  description = "Azure OpenAI endpoint"
  value       = module.openai.endpoint
}

output "openai_default_deployment_name" {
  description = "Azure OpenAI default deployment name"
  value       = module.openai.default_deployment_name
}

output "openai_advanced_deployment_name" {
  description = "Azure OpenAI advanced deployment name"
  value       = module.openai.advanced_deployment_name
}

output "openai_embedding_deployment_name" {
  description = "Azure OpenAI embedding deployment name"
  value       = module.openai.embedding_deployment_name
}
