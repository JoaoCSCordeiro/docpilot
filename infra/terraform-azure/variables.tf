variable "subscription_id" {
  description = "ID da subscricao Azure (vem de terraform.tfvars, nunca commitado)"
  type        = string
}

variable "location" {
  description = "Regiao Azure. A subscricao Azure for Students so permite swedencentral, polandcentral, germanywestcentral, francecentral e norwayeast"
  type        = string
  default     = "swedencentral"
}

variable "project_name" {
  description = "Prefixo usado no nome de todos os recursos"
  type        = string
  default     = "docpilot"
}

variable "groq_api_key" {
  description = "Chave da Groq, guardada no Key Vault"
  type        = string
  sensitive   = true
}

variable "api_image_tag" {
  description = "Tag da imagem da API no ACR. Vazio = ainda sem imagem: o Container App nao e criado"
  type        = string
  default     = ""
}

variable "qdrant_image" {
  description = "Imagem do Qdrant (sidecar). A mesma versao do docker-compose e do CI"
  type        = string
  default     = "docker.io/qdrant/qdrant:v1.19.0"
}

variable "min_replicas" {
  description = "Replicas minimas. 1 durante a demonstracao (evita cold starts de uma imagem grande), 0 para escalar a zero"
  type        = number
  default     = 1
}

variable "max_replicas" {
  description = "Replicas maximas. 1: o Qdrant e a cache LLM vivem dentro da replica"
  type        = number
  default     = 1
}

variable "log_analytics_daily_quota_gb" {
  description = "Limite diario de ingestao no Log Analytics, para o custo ter teto"
  type        = number
  default     = 0.1
}

variable "enable_azure_openai" {
  description = "Cria uma conta Azure OpenAI com um deployment pequeno para o smoke test do provider"
  type        = bool
  default     = false
}

variable "azure_openai_model" {
  description = "Modelo e versao do deployment Azure OpenAI"
  type = object({
    name     = string
    version  = string
    sku      = string
    capacity = number
  })
  default = {
    # O gpt-4o-mini 2024-07-18 ainda aparece na quota mas o deploy falha com
    # ServiceModelDeprecated (desde 2026-03-31). O gpt-4.1-mini tem quota so em
    # GlobalStandard nesta subscricao (o pedido pode ser processado fora da regiao).
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
    sku     = "GlobalStandard"
    # Capacidade em milhares de tokens/minuto (paga-se por token, nao por capacidade).
    # Com 1 (1K TPM) um so prompt RAG com 5 chunks e max_tokens 1024 deu 429.
    capacity = 10
  }
}

variable "budget_amount" {
  description = "Orcamento mensal do resource group, na moeda da subscricao. 0 desliga o budget"
  type        = number
  default     = 5
}

variable "budget_start_date" {
  description = "Primeiro dia do mes em que o budget comeca (RFC3339)"
  type        = string
  default     = "2026-10-01T00:00:00Z"
}

variable "alert_email" {
  description = "Email que recebe os alertas do budget"
  type        = string
  default     = ""
}
