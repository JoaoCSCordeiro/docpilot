# Setup local via Docker Compose

## Pré-requisitos

- Docker e Docker Compose instalados.
- Uma `GROQ_API_KEY` válida (grátis em https://console.groq.com), se
  quiseres respostas reais do agente e não só o retrieval/indexação.

## Passos

1. Copiar `.env.example` para `.env` e preencher `GROQ_API_KEY`. As
   restantes variáveis já têm valores por omissão sensatos para correr
   tudo via Compose (`docker-compose.yml` lê este `.env` para preencher
   as variáveis do serviço `api`).

   ```
   cp .env.example .env
   ```

2. Subir os três serviços (Qdrant, MongoDB, API):

   ```
   docker compose up -d --build
   ```

   Na primeira vez, o build da imagem `api` demora alguns minutos (instala
   `torch`/`sentence-transformers`). Arranques seguintes reutilizam a
   camada de dependências, a não ser que `requirements.txt` mude.

3. Indexar o corpus de documentação (`data/raw`) no Qdrant. Este passo
   corre dentro do container `api`, para usar exatamente as mesmas
   dependências e configuração que a API:

   ```
   docker compose exec api python scripts/index_documents.py
   ```

4. Confirmar que a API está operacional:

   - Swagger UI: http://localhost:8000/docs
   - Qdrant dashboard: http://localhost:6333/dashboard

5. Fazer uma pergunta:

   ```
   curl -X POST http://localhost:8000/query \
     -H "Content-Type: application/json" \
     -d "{\"question\": \"O que e o ASL Translator?\"}"
   ```

   Cada resposta fica também gravada em MongoDB (coleção `query_traces`,
   base de dados `docpilot` — ver `docs/mongodb-query-log.md`). Para
   inspecionar diretamente:

   ```
   docker compose exec mongo mongosh docpilot --eval "db.query_traces.find().sort({created_at:-1}).limit(1)"
   ```

## Parar e limpar

```
docker compose down
```

Os dados do Qdrant e do MongoDB ficam em volumes nomeados
(`qdrant_storage`, `mongo_data`) e sobrevivem a `docker compose down`.
Para os apagar também:

```
docker compose down -v
```

## Notas

- O serviço `api` liga-se ao Qdrant e ao MongoDB pelos nomes dos
  serviços na rede interna do Compose (`qdrant`, `mongo`), não por
  `localhost` — só faz sentido usar `localhost` quando corres a API
  fora do Docker, diretamente na máquina host (nesse caso, usa o
  `.env` sem alterações, como já acontecia antes deste bloco).
- Sem `GROQ_API_KEY` definida, a indexação e o retrieval funcionam
  normalmente, mas qualquer pergunta ao agente falha ao tentar gerar a
  resposta (a chamada à Groq é o único ponto que exige a chave).
