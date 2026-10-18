# Azure architecture (Block 21)

DocPilot was deployed once to a real Azure subscription (Azure for Students)
with Terraform, verified end to end, and then destroyed. The environment is
meant to be short-lived: `terraform apply` brings it up for a demonstration
and `terraform destroy` removes it, so the public URL and the credit spend
only exist while it is being shown. What was run, with dates and numbers, is
in `docs/azure-deployment-evidence.md`.

## Diagram

```text
                       Internet (HTTPS)
                              |
                              v
  +------------------- Container Apps Environment (consumption) -----------+
  |  Container App ca-docpilot-api   (1 replica, 2 vCPU / 4 GiB in total)   |
  |  +-------------------------------+   localhost   +-------------------+ |
  |  | api  (FastAPI + LangGraph)    | ------------> | qdrant v1.19.0    | |
  |  | 1.5 vCPU / 3 GiB              |   :6333       | 0.5 vCPU / 1 GiB  | |
  |  | indexes data/raw at start-up  |               | ephemeral storage | |
  |  +-------------------------------+               +-------------------+ |
  +-----|-----------|-----------------|------------------------------------+
        |           |                 | stdout/stderr
        |           |                 v
        |           |        Log Analytics workspace (30 days, daily cap)
        |           |
        |           +--> Cosmos DB for MongoDB (free tier): query log
        |
        +--> Groq API (generation; key from Key Vault)

  User-assigned managed identity
    - AcrPull on the Container Registry (image pull, no admin user)
    - Key Vault Secrets User on the Key Vault (groq-api-key, mongo-uri)

  Optional: Azure OpenAI account with a gpt-4.1-mini deployment, used only by
  the provider smoke test (the deployed API keeps generating with Groq).
  Budget on the resource group with e-mail alerts.
```

## Resources (`infra/terraform-azure`)

- Resource group `rg-docpilot` in `swedencentral`. The Azure for Students
  subscription has an "Allowed resource deployment regions" policy limited
  to swedencentral, polandcentral, germanywestcentral, francecentral and
  norwayeast; Sweden Central has both Container Apps and Azure OpenAI quota
  for this subscription.
- Container Registry, Basic SKU, admin user disabled. The Container App pulls
  with the managed identity (`AcrPull`).
- Key Vault (RBAC mode, 7-day soft delete, purged on destroy) holding the
  Groq key and the Cosmos DB connection string. The Container App reads them
  as Key Vault references through the managed identity; neither value appears
  in the Container App definition. Terraform waits 60 s after the role
  assignments because RBAC propagation is not immediate.
- Cosmos DB for MongoDB (RU), free tier, MongoDB 7.0, one database with 400
  RU/s of shared throughput, inside the free 1000 RU/s. It replaces the
  MongoDB container for the query log; `pymongo` code is unchanged.
- Log Analytics workspace (30-day retention, configurable daily ingestion
  cap) receiving the Container Apps console logs.
- Container Apps Environment (consumption) and one Container App with two
  containers: the API and Qdrant as a sidecar.
- Optional Azure OpenAI account (`enable_azure_openai`) with one Standard
  deployment.
- Budget on the resource group (e-mail alerts at 50 % actual and 100 %
  forecast).

Names of globally unique resources carry a random suffix, and the provider is
configured to purge soft-deleted Key Vaults, Cognitive Services accounts and
Log Analytics workspaces on destroy, so the environment can be recreated
right after it is destroyed.

## Decisions

- Qdrant as a sidecar with ephemeral storage, re-indexed at start-up.
  Container Apps volumes are Azure Files (SMB), and Qdrant's documentation
  advises against network file systems for its storage. The corpus is small
  (5 documents, 167 chunks), so the replica indexes `data/raw` before
  `uvicorn` starts (`scripts/index_if_empty.py`, enabled with
  `INDEX_ON_STARTUP=true`), using the same ingestion code as
  `scripts/index_documents.py`. The startup probe keeps traffic away until
  `/health` answers. A local check of this path gave identical reranked
  results to the local index on all 53 main-corpus dev questions (see the
  evidence document). For a larger corpus this would become a managed
  vector store or a Qdrant node with a managed disk.
- One replica (`max_replicas = 1`): the Qdrant index, the SQLite LLM cache
  and the in-memory token bucket live inside the replica. Scaling out would
  need the Redis backends from Block 20 (Azure Cache for Redis) and a shared
  Qdrant. Azure Cache for Redis was left out on cost.
- `min_replicas = 1` during a demonstration. The image is about 1.2 GB
  compressed; scaling from zero would pull it and re-index on the first
  request. Set `min_replicas = 0` to scale to zero between requests.
- Models are baked into the image (`Dockerfile`), so a new replica does not
  download them from Hugging Face.
- The deployed API generates with Groq, as locally. The Azure OpenAI
  provider exists behind `LLM_PROVIDER=azure_openai`, but switching the
  deployed generator would change the answers the held-out evaluation
  measured.
- Terraform state is local and gitignored: it contains the Cosmos DB
  connection string and the Groq key. A team setup would use an
  `azurerm` backend in a storage account with state locking.

## AWS and Azure mapping

| Concern | AWS module (`infra/terraform`) | Azure module (`infra/terraform-azure`) |
|---|---|---|
| Compute | ECS Fargate service | Container Apps (consumption) |
| Registry | ECR | Azure Container Registry (Basic) |
| Image pull auth | Task execution role | User-assigned identity with `AcrPull` |
| Secrets | Plain task environment variable (`GROQ_API_KEY`) | Key Vault references via managed identity |
| Network | VPC, public subnets, internet gateway | Managed by the Container Apps Environment |
| Logs | CloudWatch Logs | Log Analytics workspace |
| Vector store | Not provisioned | Qdrant sidecar, re-indexed at start-up |
| Query log | Not provisioned | Cosmos DB for MongoDB (free tier) |
| LLM | Groq | Groq; Azure OpenAI deployment for the provider smoke test |
| Status | Defined and validated (`terraform validate`), not applied | Applied once, verified, destroyed |

## Executed vs. only defined

- Executed against Azure: everything in this module, once (see the evidence
  document for dates, durations and the measured cost).
- Run locally, not deployed: the Azure Function (`functions/`, blob trigger
  that re-indexes an uploaded document) runs with Azure Functions Core Tools
  against Azurite. It was not deployed because it imports the full
  retrieval stack (PyTorch, sentence-transformers) and the deployed Qdrant is
  an ephemeral sidecar that a separate Function could not reach.
- Validated in CI only: `terraform fmt -check`, `terraform validate` and
  `tflint` (with the `azurerm` ruleset) run on every push for both Terraform
  modules; CI never runs `plan` or `apply`.
