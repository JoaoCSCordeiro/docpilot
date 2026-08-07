# Histórico de queries em MongoDB — nota de decisão

## O que é gravado

Cada vez que o agente (Bloco 7) responde a uma pergunta — via API
(`POST /query`) ou via `scripts/ask_agent.py` — um documento é gravado na
coleção `query_traces` (base de dados `docpilot`, Mongo local via
`docker-compose.yml`):

```json
{
  "question": "Como funciona o ASL Translator?",
  "retrieved_chunks": [
    {"source": "asl-translator-readme.md", "position": 0, "score": 0.55}
  ],
  "reranked_chunks": [
    {"source": "asl-translator-readme.md", "position": 0, "score": 2.3}
  ],
  "confidence": 0.91,
  "is_confident": true,
  "answer": "...",
  "created_at": "2026-08-07T01:11:16.334Z"
}
```

## Porquê MongoDB e não SQL para isto

Um trace de query tem um número variável de chunks recuperados e
reordenados, cada um com os seus próprios campos (`source`, `position`,
`score`). Modelar isto em SQL exigiria uma tabela `queries` mais uma
tabela filha `retrieved_chunks` (com foreign key), e outra para
`reranked_chunks` — dois joins só para reconstruir um único trace. Em
MongoDB, os chunks vivem como arrays de subdocumentos dentro do próprio
documento da query: sem joins, e a estrutura mapeia diretamente para o
estado do agente (`AgentState`, `src/agent/graph.py`) sem tradução
adicional.

Isto contrasta deliberadamente com o log de uso da Groq (Bloco 7,
`logs/groq_usage.log`), que **não** foi migrado para Mongo — esse é um
schema plano (timestamp + 3 inteiros + texto), sem nada de aninhado, e
já bem servido por um ficheiro de texto simples. Trocar esse caso para
Mongo seria adicionar uma dependência sem benefício real; o caso do
histórico de queries é diferente porque os dados são genuinamente
hierárquicos.

## O que isto permite (e não seria trivial em SQL sem esforço extra)

- `get_recent_queries(collection, limit)` — últimas N queries, mais
  recentes primeiro.
- `get_low_confidence_queries(collection, threshold)` — todas as
  queries onde `confidence < threshold`, úteis para auditar onde o
  guardrail está a recusar e porquê, sem precisar de abrir o
  `logs/groq_usage.log` nem repetir manualmente as perguntas.

## Testes

`tests/test_query_log.py` usa `mongomock` (Mongo inteiramente em
memória, sem servidor real) — mesmo princípio já aplicado no projeto
para o Qdrant (`QdrantClient(location=":memory:")`, Bloco 4) e para a
Groq (`FakeLLM`, Bloco 7): nenhum teste automatizado depende de um
serviço externo a correr.
