# Evidencia de deployment no k3s

Este ficheiro regista o output real (nao simulado) de `kubectl` contra um
cluster k3s a correr dentro do WSL2, apos aplicar os manifests de
`infra/k8s/` (ver `docs/k3s-setup.md` para os passos de instalacao e
`infra/k8s/README.md` para os passos de deployment).

Sem informacao sensivel em texto plano: nao ha chaves, tokens, IPs
publicos ou nomes de utilizador Windows nesta captura — apenas nomes de
recursos Kubernetes e o hostname interno da maquina de desenvolvimento
(`laptop-q99v7r1v`), que nao identifica nada sensivel.

## Estado do cluster

```
$ kubectl get nodes
NAME              STATUS   ROLES           AGE   VERSION
laptop-q99v7r1v   Ready    control-plane   19m   v1.36.3+k3s1
```

## Pods

```
$ kubectl get pods -o wide
NAME                            READY   STATUS    RESTARTS   AGE   IP           NODE              NOMINATED NODE   READINESS GATES
docpilot-api-7b55ff48fd-689jc   1/1     Running   0          76s   10.42.0.28   laptop-q99v7r1v   <none>           <none>
```

## Services

```
$ kubectl get services -o wide
NAME           TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE     SELECTOR
docpilot-api   NodePort    10.43.234.174   <none>        8000:30080/TCP   9m52s   app=docpilot-api
kubernetes     ClusterIP   10.43.0.1       <none>        443/TCP          21m     <none>
```

## Deployment

```
$ kubectl get deployment docpilot-api
NAME           READY   UP-TO-DATE   AVAILABLE   AGE
docpilot-api   1/1     1            1           9m52s
```

## Logs da aplicacao (arranque real dentro do pod)

```
$ kubectl logs -l app=docpilot-api --tail=40
/usr/local/lib/python3.11/site-packages/langgraph/checkpoint/base/__init__.py:18: LangChainPendingDeprecationWarning: The default value of `allowed_objects` will change in a future version. Pass an explicit value (e.g., allowed_objects='messages' or allowed_objects='core') to suppress this warning.
  from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     10.42.0.1:63924 - "GET /docs HTTP/1.1" 200 OK
```

A ultima linha e o pedido real feito no passo seguinte (via `curl`,
atraves do `NodePort`) — nao um log de exemplo.

## Teste de acesso real via NodePort

```
$ curl -s -o /dev/null -w "HTTP %{http_code}\n" http://<node-ip>:30080/docs
HTTP 200
```

`<node-ip>` e o IP interno do no dentro do WSL2 (`kubectl get nodes -o
jsonpath='{.items[0].status.addresses[0].address}'`), omitido aqui por
ser um IP interno efemero (muda entre reinicios do WSL2) sem valor como
prova — o que importa e o resultado, `HTTP 200`, confirmando que o
`Service` do tipo `NodePort` encaminha corretamente ate ao container.

## Nota sobre estabilidade do ambiente WSL2 durante os testes

Durante a validacao encontraram-se dois problemas reais, ambos
documentados em detalhe no `APRENDIZAGEM.md` (Bloco 14):

1. O kubelet do k3s recusava-se a arrancar em modo cgroup hibrido
   (v1/v2), o comportamento por omissao do WSL2 — corrigido forcando
   cgroup v2 puro via `.wslconfig`.
2. O `NodePort` nao respondia (embora o pod estivesse `Running`/`Ready`)
   porque a imagem WSL2 do Ubuntu nao tinha os binarios
   `iptables-save`/`iptables-restore` que o `kube-proxy` precisa —
   corrigido com `apt-get install iptables`.

Ambos os problemas sao especificos do ambiente WSL2, nao do k3s em si
nem dos manifests do DocPilot — resolvidos uma unica vez ao nivel do
sistema operativo, nao por bloco de trabalho.
