# Observabilidade com Langfuse (self-hosted) - evidência real

Execução de 2026-10-16 contra uma instância local do Langfuse, sem conta
cloud: plataforma `4.59.0` (`docker-compose.observability.yml`), SDK Python
`langfuse` 5.0.1 (OpenTelemetry), Groq `openai/gpt-oss-120b` em free tier.
Instância criada de raiz para esta evidência (volumes limpos), com
organização, projeto, chaves e utilizador criados por `LANGFUSE_INIT_*`.

## Como correr

```
cp .env.observability.example .env.observability   # e gerar valores aleatórios
docker compose -f docker-compose.observability.yml --env-file .env.observability up -d
# no .env da aplicação:
#   LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY = LANGFUSE_INIT_PROJECT_* de cima
#   LANGFUSE_BASE_URL=http://localhost:3000
```

UI em `http://localhost:3000` (login com `LANGFUSE_INIT_USER_EMAIL` /
`LANGFUSE_INIT_USER_PASSWORD`). Sem as duas chaves no `.env`, o tracing é
um no-op e nada muda no comportamento da aplicação.

Memória medida com `docker stats` logo após o arranque: web 1.45 GiB,
worker 858 MiB, ClickHouse 290 MiB, Postgres 84 MiB, MinIO 61 MiB, Redis
11 MiB, cerca de 2.75 GiB no total. É por isso que corre num compose à
parte e sem política de restart.

## Estrutura de um trace

```
docpilot-query (agent)              input: pergunta    output: resposta, decisão, confiança
├── retrieve (retriever)            top_k, coleção, modelo de embeddings -> chunks (source, position, score)
├── rerank (span)                   modelo do cross-encoder -> chunks reordenados
├── assess_confidence (guardrail)   confidence, is_confident, threshold
└── generate_answer (chain)         ou refuse (span), conforme a decisão
    └── llm (generation)            modelo, prompt, resposta, tokens input/output,
                                    custo estimado, cache_hit, rate_limit_wait_seconds
```

Pelo MCP, o SDK `mcp` 2.x cria o seu próprio span OpenTelemetry por
`tools/call` (`ask_docpilot` ou `search_docs`, tipo `TOOL` no Langfuse). Como
traz atributos `gen_ai.*`, o filtro por omissão do Langfuse exporta-o, e
o trace do DocPilot fica por baixo dele. Os pedidos têm a tag da entrada
(`api`, `mcp` ou `cli`).

O custo é **estimado** com o preço público do modelo em
`console.groq.com/docs/model/openai/gpt-oss-120b`, consultado a 2026-10-16:
$0.15 por milhão de tokens de input e $0.60 por milhão de output
(configurável em `GROQ_PRICE_*`). No free tier o custo real é zero; o valor
serve para saber quanto custaria o mesmo tráfego num plano pago.

## Execução: 15 traces

Pedidos feitos com `httpx` para `POST /query` (8), com o cliente stdio do
SDK MCP (3 + 3 repetidos depois de uma correção, ver abaixo) e com
`scripts/ask_agent.py` (1). Exportados da API pública do Langfuse
(`api.observations.get_many`) para `traces-summary.json`.

| # | Hora (UTC) | Entrada | Raiz | Pergunta | Decisão | Cache LLM | Tokens in/out | Custo estimado (USD) | Latência (s) |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 01:45:23 | api | `docpilot-query` | Que biblioteca é usada para detetar a mão e extrair os pontos-chave (l | answered | hit | 0/0 | 0.00000000 | 4.031 |
| 2 | 01:45:27 | api | `docpilot-query` | Que classificador de Machine Learning tradicional é usado para reconhe | answered | miss | 752/66 | 0.00015240 | 0.865 |
| 3 | 01:45:27 | api | `docpilot-query` | Que tecnologia de mensageria assíncrona o TrendPulse AI usa entre o ML | answered | hit | 0/0 | 0.00000000 | 0.229 |
| 4 | 01:45:28 | api | `docpilot-query` | Que modelo scikit-learn o TrendPulse AI usa para prever o retorno do d | answered | miss | 761/200 | 0.00023415 | 0.786 |
| 5 | 01:45:29 | api | `docpilot-query` | What types of HTTP authentication does Requests support? | answered | miss | 809/232 | 0.00026055 | 0.884 |
| 6 | 01:45:29 | api | `docpilot-query` | Which server does FastAPI use to run the application? | answered | miss | 761/113 | 0.00018195 | 0.730 |
| 7 | 01:45:30 | api | `docpilot-query` | Qual é a receita tradicional de bacalhau à brás? | refused | - | - | - | 0.182 |
| 8 | 01:45:30 | api | `docpilot-query` | Em que duas bibliotecas o FastAPI se baseia, segundo a secção de Requi | refused | - | - | - | 0.181 |
| 9 | 01:46:08 | mcp | `docpilot-search` | Financial Crew retries with exponential backoff | - | - | - | - | 3.406 |
| 10 | 01:46:14 | mcp | `ask_docpilot` | Which library does Financial Crew use for automatic retries with expon | answered | miss | 737/70 | 0.00015255 | 1.233 |
| 11 | 01:46:15 | mcp | `ask_docpilot` | Quem ganhou o campeonato do mundo de futebol de 2010? | refused | - | - | - | 0.262 |
| 12 | 01:47:49 | mcp | `search_docs` | Financial Crew retries with exponential backoff | - | - | - | - | 5.594 |
| 13 | 01:47:55 | mcp | `ask_docpilot` | Quem ganhou o campeonato do mundo de futebol de 2010? | refused | - | - | - | 0.214 |
| 14 | 01:47:55 | mcp | `ask_docpilot` | Which library does Financial Crew use for automatic retries with expon | answered | hit | 0/0 | 0.00000000 | 0.719 |
| 15 | 01:49:32 | cli | `docpilot-query` | Que classificador de Machine Learning tradicional é usado para reconhe | answered | hit | 0/0 | 0.00000000 | 3.486 |

Totais: 5 chamadas reais à Groq (3820 tokens de input, 681 de output,
custo estimado de $0.00098), 4 cache hits, 4 recusas e 2 pesquisas sem LLM. As latências
acima de 3 s (1, 9, 12 e 15) são primeiros pedidos de um processo novo, que
carregam os modelos de embeddings e de reranking.

Traces completos exportados (texto longo truncado a 700 caracteres, sem
metadados internos do SDK):

- `trace-api-answered.json`: pedido 6, resposta correta (Uvicorn).
- `trace-api-refused-near-threshold.json`: pedido 8, recusado com
  confiança 0.4616, perto do threshold de 0.5. É a falha cross-lingual
  documentada (pergunta em PT sobre o README do FastAPI, em inglês): o
  documento certo não chega ao top 5 e o guardrail recusa em vez de
  responder com o contexto errado.
- `trace-api-unfaithful-answer.json`: pedido 4, ver abaixo.
- `trace-mcp-search-docs.json`: pedido 12, `search_docs` com o span `TOOL`
  do SDK MCP como raiz.
- `trace-mcp-ask-answered.json`: pedido 10, `ask_docpilot` com chamada real
  à Groq (resposta correta: `tenacity`).

## O que os traces mostraram

**Uma resposta errada que passou o guardrail (pedido 4).** "Que modelo
scikit-learn o TrendPulse AI usa para prever o retorno do dia seguinte?"
recebeu "RandomForestClassifier", mas o README do TrendPulse diz
`RandomForestRegressor` (linhas 85, 116 e 127). O trace mostra porquê. No
`rerank`, o chunk com a resposta certa não está no top 5. Está lá
`asl-translator-readme.md#2`, que contém `RandomForestClassifier` (é o
classificador do tradutor de língua gestual), e o LLM atribuiu-o ao
TrendPulse. O guardrail deixou passar (`confidence` 0.7726), porque o
chunk do topo é a introdução do TrendPulse: relevante para o tema, sem a
resposta. É uma falha de fidelidade que a avaliação só de retrieval não
apanha. O Bloco 18 (LLM-as-a-judge) existe para medir este tipo de caso.

**Um bug de inicialização encontrado pelo tracing.** Na primeira sessão
MCP, o `search_docs` (pedido 9) apareceu sem o span `TOOL`, e os
`ask_docpilot` seguintes apareceram com ele. A causa: o cliente Langfuse
era criado de forma lazy dentro da primeira tool, e o middleware
OpenTelemetry do SDK MCP abre o span do `tools/call` antes de a tool
correr. Nesse primeiro pedido ainda não havia `TracerProvider`. Corrigido
inicializando o Langfuse no arranque de `scripts/run_mcp_server.py`; na
repetição (pedido 12) o span aparece.

## Degradação graciosa

- **Sem chaves**: no-op (testado em `tests/test_tracing.py`).
- **Com chaves mas Langfuse em baixo** (`docker compose ... stop
  langfuse-web`): `scripts/ask_agent.py` respondeu normalmente (exit 0),
  com um aviso `Failed to export spans batch due to timeout, max retries or
  shutdown.` no stderr. O trace desse pedido perde-se. Tempo total do
  script: 21 s, contra 17 s com o Langfuse ativo para a mesma pergunta
  (uma amostra de cada, incluindo carregamento dos modelos; a diferença
  vem da espera do `flush()` final da CLI).
- **Testes**: `tests/conftest.py` desliga o tracing em todos os testes,
  mesmo que o `.env` local tenha chaves. Os testes de tracing usam o SDK
  real com um `InMemorySpanExporter` do OpenTelemetry, sem rede.

## MongoDB e Langfuse: porque ficam os dois

| | MongoDB (`query_traces`) | Langfuse |
|---|---|---|
| Para quê | Histórico próprio da aplicação, auditoria, consultas ad-hoc (`get_low_confidence_queries`) | Debugging e análise: árvore de spans, latência por passo, tokens, custo, filtros por tag |
| Esquema | Um documento por pergunta, definido pela aplicação | Modelo de traces/observações do Langfuse (OpenTelemetry) |
| Dependência | Um container, parte do stack principal | Seis containers, cerca de 2.75 GiB de RAM, opcional |
| Falha | Escrita síncrona no pedido (no MCP é tolerada) | Export em background; pedidos continuam se falhar |

Vale a pena manter ambos neste projeto porque têm donos diferentes: o
histórico no Mongo é dado da aplicação (pode alimentar uma funcionalidade,
por exemplo rever perguntas recusadas), enquanto o Langfuse é ferramenta
de operação, ligada e desligada por configuração. Num produto real, o
Mongo podia ser dispensado se o Langfuse fosse obrigatório e retido; aqui
não é, por isso o Mongo continua a ser a única fonte de histórico garantida.

## Limitações

- O desconto da Groq para tokens de input em cache ($0.075/M) não é
  modelado: o `usage_metadata` do `langchain-groq` 0.2 não separa esses
  tokens. Sem cache do lado da Groq, a estimativa é exata; com cache,
  sobrestima.
- A API FastAPI não faz `flush()` por pedido (export em background); se o
  processo for morto, os últimos traces podem perder-se. O servidor MCP faz
  `flush()` no fim de cada tool, porque o cliente pode terminar o processo
  a qualquer momento.
- Testado com a API e o servidor MCP a correr no `.venv` local. O serviço
  `api` do `docker-compose.yml` não recebe as variáveis `LANGFUSE_*`, por
  isso em Docker o tracing fica desligado (no-op). Ligá-lo exigiria passar
  as chaves e um `LANGFUSE_BASE_URL` alcançável a partir do container (ex.:
  `http://host.docker.internal:3000`), o que não foi testado.
- `list_sources` não é instrumentado (é uma contagem no Qdrant, sem
  decisão nem LLM).
- Não foi usado o `CallbackHandler` de LangChain do Langfuse: na v5 ele
  exige `langchain-core>=1`, e o projeto usa `langchain-core` 0.3 (via
  `langgraph` 0.2). A instrumentação é manual.
- Screenshots da UI não foram tiradas nesta sessão (a extensão de browser
  não estava ligada); a evidência são os exports JSON da API do Langfuse.
