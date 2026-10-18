output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_name" {
  value = azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "api_url" {
  description = "URL publico da API (vazio enquanto api_image_tag nao estiver definido)"
  value       = local.deploy_api ? "https://${azurerm_container_app.api[0].ingress[0].fqdn}" : ""
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "cosmosdb_account_name" {
  value = azurerm_cosmosdb_account.main.name
}

output "log_analytics_workspace_id" {
  description = "Customer ID do workspace, para az monitor log-analytics query"
  value       = azurerm_log_analytics_workspace.main.workspace_id
}

output "azure_openai_endpoint" {
  value = var.enable_azure_openai ? azurerm_cognitive_account.openai[0].endpoint : ""
}

output "azure_openai_deployment" {
  value = var.enable_azure_openai ? azurerm_cognitive_deployment.openai[0].name : ""
}

output "container_app_environment_mode" {
  value = azapi_resource.container_app_environment.output.properties.environmentMode
}
