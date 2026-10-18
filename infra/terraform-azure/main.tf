data "azurerm_client_config" "current" {}

# ACR, Key Vault, Cosmos DB e Azure OpenAI tem nomes globais: o sufixo evita colisoes e
# permite recriar o ambiente logo depois de um destroy.
resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  name          = "${var.project_name}-${random_string.suffix.result}"
  compact_name  = "${var.project_name}${random_string.suffix.result}"
  deploy_api    = var.api_image_tag != ""
  api_image     = "${azurerm_container_registry.main.login_server}/docpilot-api:${var.api_image_tag}"
  enable_budget = var.budget_amount > 0 && var.alert_email != ""
  tags = {
    project = var.project_name
  }
}

resource "azurerm_resource_group" "main" {
  name     = "rg-${var.project_name}"
  location = var.location
  tags     = local.tags
}

# --- Observabilidade ---

resource "azurerm_log_analytics_workspace" "main" {
  name                = "log-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  # 30 dias de retencao estao incluidos no preco da ingestao.
  retention_in_days = 30
  daily_quota_gb    = var.log_analytics_daily_quota_gb
  tags              = local.tags
}

# --- Identidade e registry ---

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${local.name}-api"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

resource "azurerm_container_registry" "main" {
  name                = "acr${local.compact_name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  # Sem utilizador admin: o Container App faz pull com a managed identity.
  admin_enabled = false
  tags          = local.tags
}

resource "azurerm_role_assignment" "api_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# --- Segredos ---

resource "azurerm_key_vault" "main" {
  name                       = "kv-${local.name}"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

resource "azurerm_role_assignment" "deployer_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "api_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# As atribuicoes RBAC demoram a propagar; sem esta espera a escrita dos segredos e a
# leitura pelo Container App falham com 403 no primeiro apply.
resource "time_sleep" "rbac_propagation" {
  create_duration = "60s"

  depends_on = [
    azurerm_role_assignment.deployer_secrets_officer,
    azurerm_role_assignment.api_secrets_user,
    azurerm_role_assignment.api_acr_pull,
  ]
}

resource "azurerm_key_vault_secret" "groq_api_key" {
  name         = "groq-api-key"
  value        = var.groq_api_key
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [time_sleep.rbac_propagation]
}

resource "azurerm_key_vault_secret" "mongo_uri" {
  name         = "mongo-uri"
  value        = azurerm_cosmosdb_account.main.primary_mongodb_connection_string
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [time_sleep.rbac_propagation]
}

# --- Log de queries (Cosmos DB for MongoDB) ---

resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-${local.name}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "MongoDB"
  # Free tier: 1000 RU/s e 25 GB sem custo, uma conta por subscricao. So pode ser
  # ligado na criacao.
  free_tier_enabled    = true
  mongo_server_version = "7.0"

  capabilities {
    name = "EnableMongo"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  tags = local.tags
}

resource "azurerm_cosmosdb_mongo_database" "main" {
  name                = var.project_name
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  # Throughput partilhado pelas coleccoes, dentro dos 1000 RU/s do free tier.
  throughput = 400
}

# --- Computo ---

# azapi em vez de azurerm_container_app_environment: o azurerm 5.10 nao expoe o
# environmentMode e, sem ele, a API 2026-07-01 criou o ambiente em modo Express, que
# nao suporta sidecars nem referencias ao Key Vault nos secrets.
resource "azapi_resource" "container_app_environment" {
  type      = "Microsoft.App/managedEnvironments@2026-07-01"
  name      = "cae-${local.name}-wp"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location
  tags      = local.tags
  # O schema embutido no azapi 2.13 ainda nao conhece esta versao da API.
  schema_validation_enabled = false

  body = {
    properties = {
      environmentMode = "WorkloadProfiles"
      appLogsConfiguration = {
        destination = "log-analytics"
        logAnalyticsConfiguration = {
          customerId = azurerm_log_analytics_workspace.main.workspace_id
          sharedKey  = azurerm_log_analytics_workspace.main.primary_shared_key
        }
      }
      workloadProfiles = [
        {
          name                = "Consumption"
          workloadProfileType = "Consumption"
        }
      ]
    }
  }

  response_export_values = ["properties.environmentMode", "properties.defaultDomain"]
}

resource "azurerm_container_app" "api" {
  count = local.deploy_api ? 1 : 0

  name                         = "ca-${var.project_name}-api"
  container_app_environment_id = azapi_resource.container_app_environment.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.api.id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.api.id
  }

  secret {
    name                = "groq-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.groq_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }

  secret {
    name                = "mongo-uri"
    key_vault_secret_id = azurerm_key_vault_secret.mongo_uri.versionless_id
    identity            = azurerm_user_assigned_identity.api.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    # No plano de consumo o total da replica tem de ser um par valido (aqui 2 vCPU /
    # 4 GiB). A API leva a maior parte: carrega o e5-small, o reranker e o torch.
    container {
      name   = "api"
      image  = local.api_image
      cpu    = 1.5
      memory = "3Gi"

      env {
        name  = "INDEX_ON_STARTUP"
        value = "true"
      }
      env {
        name  = "QDRANT_HOST"
        value = "localhost"
      }
      env {
        name  = "QDRANT_PORT"
        value = "6333"
      }
      env {
        name  = "MONGO_DB_NAME"
        value = azurerm_cosmosdb_mongo_database.main.name
      }
      env {
        name        = "MONGO_URI"
        secret_name = "mongo-uri"
      }
      env {
        name        = "GROQ_API_KEY"
        secret_name = "groq-api-key"
      }
      # Uma replica so: a cache SQLite e o token bucket em memoria chegam, sem Azure
      # Cache for Redis.
      env {
        name  = "LLM_CACHE_BACKEND"
        value = "sqlite"
      }
      env {
        name  = "RATE_LIMITER_BACKEND"
        value = "memory"
      }

      # O uvicorn so arranca depois de indexar; ate la o /health falha e a replica nao
      # recebe trafego.
      startup_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        interval_seconds        = 10
        timeout                 = 5
        failure_count_threshold = 30
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }
    }

    container {
      name   = "qdrant"
      image  = var.qdrant_image
      cpu    = 0.5
      memory = "1Gi"
    }
  }

  depends_on = [time_sleep.rbac_propagation]
}

# --- Azure OpenAI (opcional, para o smoke test do provider) ---

resource "azurerm_cognitive_account" "openai" {
  count = var.enable_azure_openai ? 1 : 0

  name                  = "oai-${local.name}"
  location              = azurerm_resource_group.main.location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "OpenAI"
  sku_name              = "S0"
  custom_subdomain_name = "oai-${local.name}"
  tags                  = local.tags
}

resource "azurerm_cognitive_deployment" "openai" {
  count = var.enable_azure_openai ? 1 : 0

  name                 = var.azure_openai_model.name
  cognitive_account_id = azurerm_cognitive_account.openai[0].id

  model {
    format  = "OpenAI"
    name    = var.azure_openai_model.name
    version = var.azure_openai_model.version
  }

  sku {
    name     = var.azure_openai_model.sku
    capacity = var.azure_openai_model.capacity
  }
}

# --- Custos ---

resource "azurerm_consumption_budget_resource_group" "main" {
  count = local.enable_budget ? 1 : 0

  name              = "budget-${var.project_name}"
  resource_group_id = azurerm_resource_group.main.id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Forecasted"
    contact_emails = [var.alert_email]
  }
}
