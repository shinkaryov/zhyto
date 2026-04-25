output "web_app_id" {
  description = "ID of the web app"
  value       = azurerm_linux_web_app.main.id
}

output "web_app_name" {
  description = "Name of the web app"
  value       = azurerm_linux_web_app.main.name
}

output "web_app_url" {
  description = "Default hostname URL of the web app"
  value       = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "app_service_plan_id" {
  description = "ID of the app service plan"
  value       = azurerm_service_plan.main.id
}

output "principal_id" {
  description = "System-assigned managed identity principal ID"
  value       = azurerm_linux_web_app.main.identity[0].principal_id
}
