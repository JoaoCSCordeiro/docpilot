# Avaliação do retrieval - resultados reais

## Setup

- Dataset: `data/evaluation/qa_dataset.json`, 25 perguntas em português,
  cobrindo os 5 documentos indexáveis do corpus (`data/raw`), com a fonte
  esperada anotada manualmente para cada pergunta.
- Pipeline avaliado: `retrieve()` (bi-encoder, `top_k=5`) e, para
  `precision@1`, também depois de `rerank()` (cross-encoder).
- Corpus indexado: 167 chunks, fixed-size (500/50), Qdrant real
  (`docker compose up -d qdrant` + `scripts/index_documents.py`).
- Métrica de relevância: granularidade de **documento de origem**
  (`source`), não de chunk exato — ver "Limitações da metodologia" abaixo
  para o porquê.

## Resultados agregados

| Métrica | Valor |
|---|---|
| Recall@5 | 0.5600 |
| Precision@5 | 0.4240 |
| Precision@1 (antes do reranking) | 0.4400 |
| Precision@1 (depois do reranking) | 0.5200 |

## Achado principal: falha de retrieval cross-lingual

Ao investigar as 11 falhas de recall (44% do dataset), surgiu um padrão
claro: **não são aleatórias, estão quase todas concentradas nas
perguntas sobre documentos escritos em inglês** (`financial-crew-readme.md`,
`external/FastAPI-readme.md`, `external/psfrequests-readme.md`), enquanto
o dataset de perguntas está todo escrito em português.

Separando o dataset por idioma do documento-fonte esperado:

| Grupo | Nº perguntas | Recall@5 médio |
|---|---|---|
| Documentos em português (ASL Translator, TrendPulse AI) | 11 | **1.0000** |
| Documentos em inglês (Financial Crew, FastAPI, Requests) | 14 | **0.2143** |

Isto não é coincidência nem falta de chunks — confirmado que os 5
documentos têm contagens de chunk substanciais e proporcionais ao seu
tamanho (`asl`: 15, `FastAPI`: 51, `requests`: 7, `financial-crew`: 44,
`trendpulse`: 50 — total 167), por isso não é um problema de indexação.

**Causa provável**: `all-MiniLM-L6-v2` (o modelo de embeddings escolhido
no Bloco 4) é um modelo predominantemente treinado em inglês, não a
variante multilingue da família MiniLM. Uma query em português e um
chunk em inglês com o mesmo significado não ficam necessariamente
próximos no espaço de embeddings, mesmo que um humano reconheça
imediatamente que são sobre o mesmo assunto.

Isto é visível nos casos que **não** falharam dentro dos documentos em
inglês: a pergunta 7 ("papel do agente Orchestrator/Critic") contém os
termos `Orchestrator`/`Critic`, que aparecem literalmente no texto
inglês; a pergunta 19 ("comando... com o uv") contém `uv`, também
literal no texto; a pergunta 23 ("Python 3.10+") contém a versão exata
citada no README. Nos três casos, um termo técnico ou literal
partilhado entre os dois idiomas (nomes próprios, comandos, números de
versão) parece ter sido suficiente para aproximar os embeddings, mesmo
sem tradução — o que reforça a hipótese de que o problema é mesmo
cross-lingual, e não uma falha genérica do modelo.

## O que o reranking melhora (e o que não melhora)

Precision@1 subiu de 0.4400 para 0.5200 depois do reranking — uma
melhoria real, mas modesta, consistente com o que já tinha sido
observado no Bloco 6 (`docs/reranking-notes.md`): o cross-encoder separa
melhor os candidatos genuinamente relevantes dos restantes **dentro do
conjunto já recuperado**.

O que o reranking **não** muda, por construção: `recall@k` é idêntico
antes e depois do reranking, porque reordenar os mesmos `k` candidatos
não adiciona nem remove nenhum. As 11 falhas de recall cross-lingual
listadas acima continuam a falhar depois do reranking, pela mesma razão
já documentada no Bloco 6 — reranking não resolve um problema de
recall do estágio anterior (bi-encoder), só reordena o que já lá está.

## Casos de falha (exemplos)

```
[9] "Quais são os limites do free tier da Groq mencionados no Financial Crew?"
    esperado: financial-crew-readme.md
    recuperado: trendpulse-ai-readme.md (x5)

[24] "Que flag extra pode ser necessária ao clonar o repositório do Requests
     para evitar um erro de timestamp?"
    esperado: external/psfrequests-readme.md
    recuperado: trendpulse-ai-readme.md (x4), asl-translator-readme.md
```

Nota-se também que `trendpulse-ai-readme.md` (documento em português,
com muito vocabulário técnico genérico — API, Docker, testes, backend)
aparece como "vencedor por omissão" em quase todas as falhas, mesmo
quando semanticamente não tem nada a ver com a pergunta. É coerente com
a hipótese cross-lingual: entre um chunk em inglês pouco alinhado com a
query em português e um chunk em português tecnicamente genérico mas no
idioma certo, o segundo tende a ganhar por proximidade de idioma, não de
conteúdo.

## Limitações da metodologia desta avaliação

- **Granularidade de documento, não de chunk**: `recall_at_k`/
  `precision_at_k` (`src/evaluation/metrics.py`) tratam qualquer chunk do
  documento esperado como "relevante", não apenas o chunk exato que
  contém a resposta. Isto é uma simplificação deliberada — anotar
  manualmente o chunk exato para 25 perguntas seria frágil (muda sempre
  que a estratégia de chunking mudar) e não estava ao alcance deste
  bloco. O efeito prático é que a métrica é mais permissiva do que uma
  avaliação a nível de chunk seria.
- **Dataset pequeno (25 perguntas)**: suficiente para revelar um padrão
  claro como o cross-lingual, mas não para generalizar com confiança
  estatística fina sobre outras dimensões (ex: perguntas sobre secções
  de código vs. secções de arquitetura).
- **Sem avaliação da resposta final do LLM**: esta avaliação mede só a
  qualidade do retrieval (que chunks chegam ao contexto), não se a
  resposta gerada pelo agente (Bloco 7) está correta — são preocupações
  relacionadas mas distintas.

## Implicações para trabalho futuro

O achado cross-lingual é o resultado mais acionável deste bloco: se o
caso de uso real do DocPilot envolver perguntas em português sobre
documentação em inglês (cenário plausível e já presente neste corpus),
`all-MiniLM-L6-v2` não é a escolha certa sem mais nenhuma medida. Duas
direções óbvias, nenhuma implementada nesta fase (fora do âmbito do
Bloco 8, que é medir, não corrigir): trocar para um modelo de embeddings
multilingue (ex: `paraphrase-multilingual-MiniLM-L12-v2`) e reavaliar
com este mesmo dataset; ou traduzir a query para o idioma dominante do
corpus antes do retrieval. Qualquer uma seria uma mudança pequena e
isolada (`EMBEDDING_MODEL_NAME` já é configurável desde o Bloco 4), o
que valida a decisão de a ter tornado configurável desde o início.
