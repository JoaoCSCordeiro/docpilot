# Servidor MCP - evidência real

Execuções feitas a 2026-10-16 contra o stack local real: Qdrant `v1.19.0`
com a coleção `docpilot` (167 chunks, 5 documentos), MongoDB `7.0` e a
Groq (`openai/gpt-oss-120b`, free tier). SDK `mcp` 2.3.0, Claude Code
2.1.301, Windows 10. Caminhos absolutos substituídos por `<repo>`. Os
outputs não contêm chaves nem tokens.

Chamadas à Groq feitas nesta evidência: 2 (uma por cada `ask_docpilot`
respondido; a pergunta recusada não chama o LLM). Contadas pelo número de
linhas novas em `logs/groq_usage.log`.

## 1. Registo no Claude Code

Sintaxe confirmada com `claude mcp add --help`. Scope `local`: a entrada
fica em `~/.claude.json`, associada a este projeto e a este utilizador,
sem criar ficheiros no repositório.

```
> claude mcp add docpilot --scope local -- "<repo>\.venv\Scripts\python.exe" "<repo>\scripts\run_mcp_server.py"
Added stdio MCP server docpilot with command: <repo>\.venv\Scripts\python.exe <repo>\scripts\run_mcp_server.py to local config

> claude mcp list
Checking MCP server health…
docpilot: <repo>\.venv\Scripts\python.exe <repo>\scripts\run_mcp_server.py - ✔ Connected
```

## 2. Chamada real a partir do Claude Code (headless)

```
claude -p "Use only the docpilot MCP tools. Step 1: call search_docs with query
'Que tecnologia de mensageria assíncrona usa o TrendPulse AI?' and top_k 3.
Step 2: call ask_docpilot with question 'Que tecnologia de mensageria assíncrona
o TrendPulse AI usa entre o ML Engine e o Core Backend?'. Then reply in two
short lines: ..." \
  --allowedTools "mcp__docpilot__search_docs,mcp__docpilot__ask_docpilot" \
  --output-format stream-json --verbose
```

Eventos extraídos do `stream-json` (texto dos chunks truncado aqui; o
resultado real traz o chunk completo):

```
TOOL_USE mcp__docpilot__search_docs {"query": "Que tecnologia de mensageria assíncrona usa o TrendPulse AI?", "top_k": 3}
TOOL_RESULT {"query": "...", "confidence": 0.9866611783940327, "chunks": [
  {"source": "trendpulse-ai-readme.md", "position": 0,  "score": 4.303647994995117,  "text": "# 📈 TrendPulse AI ... mensageria assíncrona e orquestração de sistemas de IA"},
  {"source": "trendpulse-ai-readme.md", "position": 36, "score": -9.9866943359375,   "text": "..."},
  {"source": "asl-translator-readme.md", "position": 11, "score": -10.219364166259766, "text": "..."}]}

TOOL_USE mcp__docpilot__ask_docpilot {"question": "Que tecnologia de mensageria assíncrona o TrendPulse AI usa entre o ML Engine e o Core Backend?"}
TOOL_RESULT {"decision": "answered",
  "answer": "O TrendPulse AI utiliza **RabbitMQ** como tecnologia de mensageria assíncrona entre o ML Engine (Python) e o Core Backend (Java), empregando a biblioteca **pika** no lado Python para publicar nas exchanges/queues e um `@RabbitListener` no Spring Boot para consumir as mensagens.",
  "confidence": 0.9398726726856143, "confidence_threshold": 0.5,
  "sources": [{"source": "trendpulse-ai-readme.md", "position": 0,  "score": 2.7492799758911133},
              {"source": "trendpulse-ai-readme.md", "position": 1,  "score": 1.2391201257705688},
              {"source": "trendpulse-ai-readme.md", "position": 45, "score": 0.5960593223571777},
              {"source": "trendpulse-ai-readme.md", "position": 25, "score": -8.859868049621582},
              {"source": "trendpulse-ai-readme.md", "position": 36, "score": -9.813785552978516}]}

RESULT success num_turns=5 duration_ms=18831
```

A resposta bate com o `expected_answer_hint` da pergunta 12 do dataset
(RabbitMQ). Os detalhes extra (`pika`, `@RabbitListener`) existem no
documento de origem (`trendpulse-ai-readme.md`, linhas 14, 83 e 320).

Nota: no arranque da sessão headless o servidor ainda estava a ligar
(`"status": "pending"`), e o modelo precisou de uma segunda pesquisa de
tools antes de as encontrar. É o tempo de arranque do processo Python
(imports de `torch`/`sentence-transformers`), não um erro do servidor.

## 3. Sessão stdio com o cliente do SDK

Script de verificação com `mcp.Client(StdioServerParameters(...))`, que
lança `scripts/run_mcp_server.py` como subprocesso **a partir de outro
diretório de trabalho**, para confirmar que a cache SQLite e o log de uso
continuam a ser escritos na raiz do repositório.

```
protocol_version=2026-07-28
server_info=docpilot
tools=search_docs, ask_docpilot, list_sources
```

`list_sources()`:

```json
{
  "collection": "docpilot",
  "total_chunks": 167,
  "sources": [
    {"source": "asl-translator-readme.md", "chunk_count": 15},
    {"source": "external/FastAPI-readme.md", "chunk_count": 51},
    {"source": "external/psfrequests-readme.md", "chunk_count": 7},
    {"source": "financial-crew-readme.md", "chunk_count": 44},
    {"source": "trendpulse-ai-readme.md", "chunk_count": 50}
  ]
}
```

`search_docs(query="Which server does FastAPI use to run the application?", top_k=3)`
(sem LLM; texto truncado a 160 caracteres):

```json
{
  "query": "Which server does FastAPI use to run the application?",
  "confidence": 0.9775785050924842,
  "chunks": [
    {"source": "external/FastAPI-readme.md", "position": 23, "score": 3.7750585079193115,
     "text": "in-a-hurry).  </details>  ### Run it  Run the server with: ... $ uv run fastapi dev [...]"},
    {"source": "external/FastAPI-readme.md", "position": 48, "score": 1.4702098369598389,
     "text": "or high performance serving. * `fastapi-cli[standard]` - to provide the `fastapi` command. [...]"},
    {"source": "external/FastAPI-readme.md", "position": 44, "score": 0.9534568190574646,
     "text": " to the cloud. 🎉  FastAPI Cloud is the primary sponsor [...]"}
  ]
}
```

`search_docs(top_k=50)`, validação de input:

```
is_error=True
Error executing tool search_docs: 1 validation error for search_docsArguments
top_k
  Input should be less than or equal to 20 [type=less_than_equal, input_value=50, input_type=int]
```

`ask_docpilot` com a pergunta 1 do dataset (respondida):

```json
{
  "decision": "answered",
  "answer": "A biblioteca utilizada para detetar a mão e extrair os pontos‑chave (landmarks) no tradutor de língua gestual é o **MediaPipe Hands**.",
  "confidence": 0.9856979738919395,
  "confidence_threshold": 0.5,
  "sources": [
    {"source": "asl-translator-readme.md", "position": 1, "score": 4.2329487800598145},
    {"source": "asl-translator-readme.md", "position": 2, "score": 2.110203742980957},
    {"source": "asl-translator-readme.md", "position": 12, "score": 1.1610758304595947},
    {"source": "asl-translator-readme.md", "position": 11, "score": -5.59459114074707},
    {"source": "trendpulse-ai-readme.md", "position": 36, "score": -5.852966785430908}
  ]
}
```

`ask_docpilot("Qual é a receita tradicional de bacalhau à brás?")`
(fora de âmbito, recusada pelo guardrail, sem chamada ao LLM):

```json
{
  "decision": "refused",
  "answer": "Não tenho informação suficiente na documentação disponível para responder com confiança a essa pergunta.",
  "confidence": 0.00012030017633917641,
  "confidence_threshold": 0.5,
  "sources": [
    {"source": "asl-translator-readme.md", "position": 11, "score": -9.025400161743164},
    {"source": "trendpulse-ai-readme.md", "position": 15, "score": -10.517658233642578},
    {"source": "asl-translator-readme.md", "position": 12, "score": -10.568056106567383},
    {"source": "trendpulse-ai-readme.md", "position": 36, "score": -10.89198112487793},
    {"source": "trendpulse-ai-readme.md", "position": 37, "score": -10.953351974487305}
  ]
}
```

As duas perguntas ficaram gravadas como traces no MongoDB
(`db.query_traces`, `is_confident: true` e `false` respetivamente).

## 4. Streamable HTTP

```
> python scripts/run_mcp_server.py --transport streamable-http   # 127.0.0.1:8001/mcp

# cliente: mcp.Client("http://127.0.0.1:8001/mcp")
protocol_version=2026-07-28
tools=search_docs, ask_docpilot, list_sources
list_sources total_chunks=167
search_docs("Requests HTTP authentication", top_k=2):
  external/psfrequests-readme.md#2  score=4.945810317993164
  external/psfrequests-readme.md#1  score=4.1364946365356445
```

## 5. Erro com o Qdrant em baixo

```
> docker compose stop qdrant
# search_docs(query="FastAPI")
is_error=True
Error executing tool search_docs: Qdrant is not reachable at localhost:6333 (ResponseHandlingException). Start it with: docker compose up -d qdrant
> docker compose start qdrant
```

## Risco de segurança: prompt injection através do conteúdo devolvido

`search_docs` devolve o texto dos chunks tal como está indexado, e
`ask_docpilot` devolve uma resposta gerada a partir desse texto. Se um
documento indexado contiver instruções ("ignora as instruções anteriores
e ..."), elas chegam ao modelo do cliente MCP como resultado de uma tool.
É um caso de prompt injection indireto: quem controla um documento
indexado pode tentar dirigir o agente cliente.

O que existe hoje:

- As `instructions` do servidor (enviadas ao cliente na ligação) dizem que
  o texto devolvido é conteúdo de documentos, não instruções, e que não
  deve ser seguido. Isto é uma indicação ao modelo, não uma garantia: um
  modelo pode ignorá-la.
- As três tools são de leitura (`read_only_hint=True`). Nenhuma tool deste
  servidor altera documentos, o índice ou o sistema do utilizador, por
  isso uma injeção não consegue usar o DocPilot para causar efeitos
  colaterais. O risco está no que o agente cliente fizer com outras tools
  que tenha disponíveis.
- O corpus atual é controlado (READMEs locais do portefólio e três
  READMEs públicos copiados manualmente), o que limita o risco na prática.
- O transporte HTTP liga-se a `127.0.0.1` por omissão; com esse host o SDK
  ativa proteção contra DNS rebinding (`Host`/`Origin` restritos a
  localhost). Não há autenticação: não deve ser exposto noutra interface.

O que não existe:

- Nenhuma filtragem ou deteção de instruções no texto dos chunks antes de
  os devolver.
- O prompt de geração usado por `ask_docpilot` não está endurecido contra
  instruções dentro do contexto; um documento envenenado pode influenciar
  a própria resposta do DocPilot. O Bloco 18 mede isto com casos de
  injeção diretos e indiretos (documentos com string canário numa coleção
  de avaliação separada).
- Se a ingestão passar a aceitar documentos arbitrários (por exemplo o
  blob trigger do Bloco 21), o risco aumenta e esta secção tem de ser
  revista.
