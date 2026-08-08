# Manifests Kubernetes (demonstracao via minikube)

Estes manifests demonstram o mesmo container da API (Bloco 10) a correr
orquestrado por Kubernetes, como alternativa ao ECS/Fargate do
`infra/terraform`. Cobrem apenas a API — Qdrant e MongoDB continuam a
correr fora do cluster (no host, via `docker-compose.yml`), acessiveis a
partir do minikube pelo hostname `host.minikube.internal`.

## Passos

1. Arrancar o minikube e apontar o Docker CLI para o daemon interno dele:

   ```
   minikube start
   eval $(minikube docker-env)
   ```

2. Construir a imagem da API dentro do daemon do minikube (sem precisar de
   a publicar em nenhum registry):

   ```
   docker build -t docpilot-api:latest -f Dockerfile .
   ```

3. Subir Qdrant e MongoDB no host (fora do minikube):

   ```
   docker compose up -d qdrant mongo
   ```

4. Criar o secret com a chave da Groq (nunca commitado em texto):

   ```
   kubectl create secret generic docpilot-secrets --from-literal=groq-api-key=<a-tua-chave>
   ```

5. Aplicar os manifests:

   ```
   kubectl apply -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
   ```

6. Aceder a API (NodePort `30080`):

   ```
   minikube service docpilot-api --url
   ```

## Limpar

```
kubectl delete -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
kubectl delete secret docpilot-secrets
minikube stop
```

## Nota sobre validacao

Estes manifests foram validados por sintaxe (YAML valido, campos
obrigatorios presentes) mas **nao foram aplicados contra um cluster real**
durante o desenvolvimento deste bloco — este ambiente nao tinha minikube
nem um cluster Kubernetes acessivel via `kubectl`. A validacao completa
(passos acima) fica pendente para quando houver acesso a um cluster local.
