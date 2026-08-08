output "ecr_repository_url" {
  description = "URL do repositorio ECR onde a imagem da API deve ser publicada"
  value       = aws_ecr_repository.api.repository_url
}

output "ecs_cluster_name" {
  description = "Nome do cluster ECS"
  value       = aws_ecs_cluster.main.name
}

output "ecs_service_name" {
  description = "Nome do servico ECS"
  value       = aws_ecs_service.api.name
}

output "vpc_id" {
  description = "ID da VPC criada"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs das subnets publicas"
  value       = aws_subnet.public[*].id
}
