# Instalacao do k3s no Windows via WSL2

k3s (distribuicao leve de Kubernetes, mantida pela Rancher/SUSE) corre em
Linux. Em Windows, a forma mais simples de o correr sem custos de cloud e
dentro do WSL2 (Windows Subsystem for Linux v2), que arranca uma VM Linux
real com o kernel Linux e o systemd necessarios.

Isto e diferente do minikube usado nos blocos anteriores: o minikube cria
um cluster Kubernetes de um so no dentro de um container/VM dedicado a
simular Kubernetes para desenvolvimento local. O k3s e uma distribuicao
Kubernetes real e completa (o mesmo binario que corre em produção em
edge/IoT e clusters pequenos), so que aqui aplicada a um unico no dentro
do WSL2.

## 1. Confirmar que o WSL2 esta ativo

```
wsl --status
wsl --version
```

Se o WSL2 ja estiver instalado e ativo (versao 2 como default), avanca
diretamente para o passo 2 — nao e preciso repetir a instalacao da
feature base, que normalmente exige reiniciar o Windows.

Se `wsl --status` falhar ou indicar que o WSL nao esta instalado, corre:

```
wsl --install
```

e reinicia o computador quando pedido.

## 2. Instalar uma distro Linux (Ubuntu)

```
wsl --install -d Ubuntu
```

Este passo e interativo: a primeira vez que o Ubuntu arranca pede para
criares um utilizador e password Linux (independentes da conta Windows).
Normalmente nao exige reiniciar o PC, porque o motor WSL2 ja esta pronto
no passo 1.

Confirmar que ficou registada:

```
wsl -l -v
```

## 3. Instalar o k3s dentro do Ubuntu

Dentro da distro (ou via `wsl -d Ubuntu -u root -- <comando>` a partir do
Windows), correr o script oficial de instalacao:

```
curl -sfL https://get.k3s.io | sh -
```

Isto instala o k3s como servico `systemd` (arranque automatico), e cria
tambem os symlinks `kubectl`, `crictl` e `ctr` a apontar para o binario
do k3s.

### Problema conhecido: cgroup v1 vs v2

Por omissao, o kernel do WSL2 arranca em modo hibrido cgroup v1/v2. O
kubelet do k3s recusa-se a arrancar nesse modo, com o erro:

```
Error: failed to validate kubelet configuration, error: kubelet is
configured to not run on a host using cgroup v1.
```

Correcao: criar/editar o ficheiro `.wslconfig` no perfil do utilizador
Windows (`C:\Users\<utilizador>\.wslconfig`, fora do WSL) com:

```ini
[wsl2]
kernelCommandLine = cgroup_no_v1=all
```

e reiniciar o WSL2 (isto para todas as distros WSL, nao so o Ubuntu —
elas voltam a arrancar normalmente da proxima vez que forem usadas):

```
wsl --shutdown
```

Confirmar que ficou em cgroup v2 puro:

```
stat -fc %T /sys/fs/cgroup/
```

Deve devolver `cgroup2fs` (em vez de `tmpfs`). Depois disto, o servico
k3s arranca sem problemas:

```
systemctl restart k3s
systemctl is-active k3s
```

## 4. Confirmar o cluster

```
kubectl get nodes
kubectl get pods -A
```

O no deve aparecer como `Ready`, e os pods de sistema (`coredns`,
`traefik`, `local-path-provisioner`, `metrics-server`) devem chegar a
`Running`/`Completed` apos cerca de um minuto.

## 5. Configurar o kubectl para o utilizador normal (sem sudo)

O instalador escreve o kubeconfig em `/etc/rancher/k3s/k3s.yaml`, so
legivel por `root`. Para o utilizador normal nao precisar de `sudo` em
cada comando:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
chmod 600 ~/.kube/config
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc
```

Abrir um novo terminal Ubuntu (ou `source ~/.bashrc`) e confirmar:

```
kubectl get nodes
```

## Aceder ao cluster a partir do PowerShell/Windows

Todos os comandos `kubectl` usados neste bloco correm de dentro do
terminal Ubuntu (WSL2), nao no PowerShell. Isto e suficiente para o
objetivo do bloco (evidencia de Kubernetes real, `kubectl` funcional) e
evita ter de manter um `kubectl.exe` e `KUBECONFIG` sincronizados no lado
Windows. Se no futuro for preciso usar `kubectl` diretamente no
PowerShell, o kubeconfig pode ser copiado de dentro do WSL2 para
`C:\Users\<utilizador>\.kube\config`, aproveitando o "localhost
forwarding" do WSL2 (a API do k3s fica acessivel via `127.0.0.1:6443`
tambem a partir do Windows).
