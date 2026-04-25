output "account_id" {
  description = "Azure OpenAI account resource ID"
  value       = azurerm_cognitive_account.openai.id
}

output "account_name" {
  description = "Azure OpenAI account name"
  value       = azurerm_cognitive_account.openai.name
}

output "endpoint" {
  description = "Azure OpenAI endpoint URL"
  value       = azurerm_cognitive_account.openai.endpoint
}

output "primary_access_key" {
  description = "Primary API key for Azure OpenAI account"
  value       = azurerm_cognitive_account.openai.primary_access_key
  sensitive   = true
}

output "default_deployment_name" {
  description = "Default chat deployment name"
  value       = azurerm_cognitive_deployment.default.name
}

output "advanced_deployment_name" {
  description = "Advanced chat deployment name"
  value       = var.enable_advanced_deployment ? azurerm_cognitive_deployment.advanced[0].name : null
}

output "embedding_deployment_name" {
  description = "Embedding deployment name"
  value       = azurerm_cognitive_deployment.embedding.name
}
