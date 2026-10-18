# Azure infrastructure (Terraform) - DocPilot

Short-lived Azure environment for DocPilot: apply it for a demonstration,
verify, destroy it. Architecture and decisions: `docs/azure-architecture.md`.
Evidence of the one run so far: `docs/azure-deployment-evidence.md`.

## Cost

Applying creates billed resources. With the defaults, the fixed cost while
the environment exists is the Container Registry (Basic, billed per day);
Container Apps compute falls inside the monthly free grant for a short
demonstration, Cosmos DB uses the free tier, Key Vault and Log Analytics are
billed per operation and per GB. With `min_replicas = 1` the replica runs (and
consumes the free grant) for as long as the app exists. **Destroy it when the
demonstration ends.** A budget with e-mail alerts is created when
`alert_email` is set.

## Prerequisites

- Terraform >= 1.5, Azure CLI logged in (`az login`), Docker.
- The subscription must allow the chosen region (Azure for Students limits
  the regions with a policy) and have the resource providers registered:
  `Microsoft.App`, `Microsoft.OperationalInsights`, `Microsoft.KeyVault`,
  `Microsoft.DocumentDB`, `Microsoft.ContainerRegistry`,
  `Microsoft.CognitiveServices`, `Microsoft.ManagedIdentity`.
- `cp terraform.tfvars.example terraform.tfvars` and fill in the values
  (`terraform.tfvars` and the state are gitignored: they hold secrets).

## Apply (two phases)

The Container App needs the image in the registry the module creates, so the
first apply runs without it:

```bash
terraform init
terraform apply                       # api_image_tag = "" : everything except the app

ACR=$(terraform output -raw acr_name)
az acr login --name "$ACR"
docker build -t "$ACR.azurecr.io/docpilot-api:v21" ../..
docker push "$ACR.azurecr.io/docpilot-api:v21"

terraform apply -var api_image_tag=v21   # creates the Container App (public URL)
terraform output api_url
python -X utf8 ../../scripts/azure_smoke_test.py "$(terraform output -raw api_url)"
```

The replica indexes `data/raw` into its Qdrant sidecar before `uvicorn`
starts; `/health` answers once that is done (under a minute in the recorded
run).

## Destroy

```bash
terraform apply -var api_image_tag=""   # optional: close the public URL first
terraform destroy
az group exists --name rg-docpilot       # false
```

Key Vault, Azure OpenAI and Log Analytics are purged on destroy, so the
environment can be recreated right away.

## Validation without a subscription

```bash
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
tflint --init && tflint
```

CI runs these on every push; it never runs `plan` or `apply`.
