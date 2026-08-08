variable "aws_region" {
  description = "Regiao AWS onde os recursos sao criados"
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Prefixo usado no nome de todos os recursos"
  type        = string
  default     = "docpilot"
}

variable "vpc_cidr" {
  description = "Bloco CIDR da VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones a usar (uma subnet publica por zona)"
  type        = list(string)
  default     = ["eu-west-1a", "eu-west-1b"]
}

variable "public_subnet_cidrs" {
  description = "Blocos CIDR das subnets publicas, na mesma ordem de availability_zones"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "container_image" {
  description = <<-EOT
    Imagem do container da API (URI completo, incluindo tag).
    Por omissao usa uma imagem placeholder publica (amazon-ecs-sample), para que
    `terraform plan`/`apply` consigam criar o cluster e o servico ECS sem
    depender de uma imagem ja publicada no ECR. Depois de correr
    `docker push` para o repositorio criado por este modulo (ver
    infra/terraform/README.md), sobrepor esta variavel com o URI real e
    reaplicar.
  EOT
  type        = string
  default     = "public.ecr.aws/aws-containers/ecsdemo-frontend:latest"
}

variable "container_port" {
  description = "Porta exposta pelo container da API"
  type        = number
  default     = 8000
}

variable "task_cpu" {
  description = "CPU units da task Fargate (256 = 0.25 vCPU)"
  type        = string
  default     = "256"
}

variable "task_memory" {
  description = "Memoria (MB) da task Fargate"
  type        = string
  default     = "512"
}

variable "desired_count" {
  description = "Numero de tasks a correr em simultaneo"
  type        = number
  default     = 1
}

variable "qdrant_host" {
  description = <<-EOT
    Host do Qdrant acessivel pela task ECS. Este modulo nao cria Qdrant/MongoDB
    em AWS (fora do escopo do Bloco 11 - ver Limitations em infra/terraform/README.md);
    o valor por omissao serve apenas para o plano/apply nao falharem por falta
    de variavel, nao aponta para nenhuma instancia real.
  EOT
  type        = string
  default     = "localhost"
}

variable "qdrant_port" {
  description = "Porta do Qdrant"
  type        = number
  default     = 6333
}

variable "mongo_uri" {
  description = "URI de ligacao ao MongoDB acessivel pela task (ver nota em qdrant_host)"
  type        = string
  default     = "mongodb://localhost:27017"
}

variable "groq_api_key" {
  description = "Chave da API da Groq, injetada como variavel de ambiente na task"
  type        = string
  default     = ""
  sensitive   = true
}
