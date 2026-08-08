# Infraestrutura AWS (Terraform) — DocPilot

## Aviso de custos

Este modulo cria recursos reais na AWS que **tem custo por hora enquanto
estiverem a correr** (Fargate task, ECR, CloudWatch Logs). Nao faz parte do
free tier da AWS. **Nao deixar isto aplicado sem necessidade** — aplicar
apenas para gravar uma demonstracao, confirmar visualmente que funciona, e
destruir logo a seguir (ver secao "Destruir" abaixo). Os custos aproximados
(regiao `eu-west-1`, valores por omissao deste modulo):

- Fargate (0.25 vCPU / 0.5 GB, 1 task): ~0.01 USD/hora
- ECR: gratuito ate 500 MB de armazenamento/mes, imagem da API e maior que
  isso (imagens com `sentence-transformers`/`torch` costumam passar de 1 GB)
- CloudWatch Logs: custo residual por armazenamento/ingestao de logs

Nenhum destes valores e alto para uma demo de poucas horas, mas **somam-se
se ficar esquecido a correr durante dias/semanas**.

## O que este modulo cria

- Uma VPC minima com duas subnets publicas, internet gateway e route table
  (sem NAT Gateway — reduz custo fixo, as tasks recebem IP publico
  diretamente)
- Um repositorio ECR (`docpilot-api`) para a imagem da API
- Um cluster ECS (Fargate) com uma task definition e um servico a correr a
  API do DocPilot

## O que este modulo **nao** cria (limitacoes conscientes)

- Qdrant e MongoDB **nao** sao aprovisionados em AWS — este modulo cobre só
  a camada de computo da API (VPC, ECR, ECS), consistente com o objetivo do
  Bloco 11 ("VPC minima, container registry, e servico de container").
  Para uma demo completa na cloud, a forma mais simples e continuar a usar
  Qdrant/MongoDB self-hosted (ex: no mesmo host, ou noutro container Fargate
  na mesma VPC) e apontar `qdrant_host`/`mongo_uri` para la.
- Sem HTTPS/load balancer — a task recebe um IP publico efemero
  diretamente, adequado para uma demonstracao pontual, nao para producao.

## Pre-requisitos

- Terraform >= 1.5 (`terraform version`)
- Conta AWS com credenciais configuradas localmente (`aws configure`, ou
  variaveis de ambiente `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`)
- Docker, para construir e publicar a imagem da API no ECR

## Passos

1. Inicializar o Terraform (descarrega o provider AWS):

   ```
   terraform init
   ```

2. Rever o plano (nao aplica nada ainda):

   ```
   terraform plan
   ```

   Por omissao, `container_image` aponta para uma imagem publica de
   demonstracao (`ecsdemo-frontend`), para que este `plan`/`apply` inicial
   nao dependa de uma imagem ja publicada no ECR.

3. Aplicar (cria os recursos reais na AWS):

   ```
   terraform apply
   ```

4. Publicar a imagem real da API no repositorio ECR criado:

   ```
   aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin $(terraform output -raw ecr_repository_url | cut -d/ -f1)
   docker build -t $(terraform output -raw ecr_repository_url):latest -f ../../Dockerfile ../..
   docker push $(terraform output -raw ecr_repository_url):latest
   ```

5. Apontar o servico para a imagem publicada e reaplicar:

   ```
   terraform apply -var="container_image=$(terraform output -raw ecr_repository_url):latest"
   ```

6. Confirmar que a task esta a correr e obter o IP publico (a AWS CLI e
   mais direta do que Terraform para isto, porque o IP so existe depois da
   task arrancar):

   ```
   aws ecs list-tasks --cluster $(terraform output -raw ecs_cluster_name)
   ```

## Destruir

**Fazer sempre isto depois de gravar a demonstracao**, para nao continuar a
pagar pelos recursos:

```
terraform destroy
```

Confirma no final que a AWS Console (ECS, ECR, VPC) nao mostra mais nenhum
recurso com o prefixo `docpilot-`.
