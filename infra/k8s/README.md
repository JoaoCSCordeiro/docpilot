# Manifests Kubernetes (minikube e k3s)

Estes manifests demonstram o mesmo container da API (Bloco 10) a correr
orquestrado por Kubernetes, como alternativa ao ECS/Fargate do
`infra/terraform`. Cobrem apenas a API; Qdrant e MongoDB continuam a
correr fora do cluster (no host, via `docker-compose.yml`).

Ha dois fluxos documentados, com propositos diferentes:

- **minikube** (Bloco 11): validar que os manifests sao sintaticamente
  corretos, sem exigir nenhuma infraestrutura extra alem do proprio
  minikube.
- **k3s** (Bloco 14, ver `docs/k3s-setup.md`): aplicar os mesmos
  manifests a uma distribuicao Kubernetes real (nao uma ferramenta de
  desenvolvimento local), como evidencia genuina de Kubernetes
  hands-on. Ver `docs/k3s-deployment-evidence.md` para o output real de
  `kubectl` contra o cluster k3s.

O hostname usado para o container aceder ao Qdrant/MongoDB no host e
`host.docker.internal` (`infra/k8s/deployment.yaml`) — funciona em ambos
os fluxos, porque o Docker Desktop injeta esta resolucao em qualquer
distro WSL2, nao so no minikube.

## Fluxo k3s (recomendado — cluster Kubernetes real)

Ver `docs/k3s-setup.md` para a instalacao completa do k3s (WSL2 +
Ubuntu + correcao de cgroups). Assumindo o cluster ja instalado e
`kubectl` configurado dentro da distro Ubuntu:

1. Subir Qdrant e MongoDB no host (fora do k3s):

   ```
   docker compose up -d qdrant mongo
   ```

2. Construir a imagem da API com o Docker Desktop (o mesmo daemon ja
   usado no Bloco 10 — k3s nao usa o daemon Docker diretamente, usa
   `containerd`):

   ```
   docker build -t docpilot-api:latest -f Dockerfile .
   ```

3. Exportar a imagem e importa-la no `containerd` do k3s (dentro da
   distro Ubuntu):

   ```
   docker save docpilot-api:latest -o docpilot-api.tar
   sudo k3s ctr images import docpilot-api.tar
   ```

4. Criar o secret com a chave da Groq (nunca commitado em texto):

   ```
   kubectl create secret generic docpilot-secrets --from-literal=groq-api-key=<a-tua-chave>
   ```

5. Aplicar os manifests:

   ```
   kubectl apply -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
   ```

6. Confirmar que ficou operacional:

   ```
   kubectl get pods
   kubectl get services
   ```

7. Aceder a API (NodePort `30080`, no IP do no dentro do WSL2):

   ```
   NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[0].address}')
   curl http://$NODE_IP:30080/docs
   ```

### Limpar

```
kubectl delete -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
kubectl delete secret docpilot-secrets
```

## Fluxo minikube (validacao rapida, sem cluster real)

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

### Limpar

```
kubectl delete -f infra/k8s/deployment.yaml -f infra/k8s/service.yaml
kubectl delete secret docpilot-secrets
minikube stop
```

## Nota sobre validacao

O fluxo k3s foi aplicado e confirmado contra um cluster real (Bloco 14) —
ver `docs/k3s-deployment-evidence.md` para o output real de `kubectl`. O
fluxo minikube foi validado apenas por sintaxe (YAML valido, campos
obrigatorios presentes) durante o Bloco 11, sem cluster minikube
disponivel nesse momento.
