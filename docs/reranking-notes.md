# Reranking - notas sobre o impacto observado

## Setup

- Retrieval inicial (bi-encoder): `all-MiniLM-L6-v2`, top-5 candidatos por
  similaridade de cosseno no Qdrant.
- Reranking: cross-encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`, aplicado
  só sobre os 5 candidatos já devolvidos pelo retriever (nao sobre todo o
  corpus).
- Corpus: `data/raw` completo (READMEs do portefolio + READMEs externos de
  referencia), chunking fixed-size (500/50), indexado num Qdrant em
  memoria para este teste.

## Caso 1 - reordenacao dentro do conjunto candidato

Query: "Como e que o TrendPulse AI deteta tendencias?"

Antes do reranking (score = similaridade de cosseno, 0 a 1):

1. 0.6046 - trendpulse-ai-readme.md#0 (introducao do projeto)
2. 0.5059 - trendpulse-ai-readme.md#36
3. 0.4971 - trendpulse-ai-readme.md#15
4. 0.4700 - asl-translator-readme.md#11
5. 0.4546 - asl-translator-readme.md#2

Depois do reranking (score = logit do cross-encoder, nao normalizado):

1. 0.8221 - trendpulse-ai-readme.md#0
2. -7.9069 - trendpulse-ai-readme.md#15
3. -10.0924 - asl-translator-readme.md#2
4. -10.2431 - asl-translator-readme.md#11
5. -10.4520 - trendpulse-ai-readme.md#36

**Observacao**: o chunk mais relevante (introducao do TrendPulse AI) ja
vinha em primeiro no bi-encoder, mas o cross-encoder separa-o com muito
mais confianca do resto (0.82 vs. o segundo lugar bem negativo) do que o
bi-encoder (0.60 vs. 0.50 - diferenca pequena, quase todos os candidatos
"parecidos"). Isto e o comportamento esperado: o bi-encoder tende a
amontoar scores num intervalo estreito porque compara embeddings gerados
independentemente da query; o cross-encoder ve query e chunk juntos, o que
lhe da uma nocao de relevancia mais discriminativa.

## Caso 2 - limitacao do reranking (nao corrige problemas de recall)

Query: "Que guardrails deterministicos existem no Financial Crew para
evitar alucinacao?"

O retrieval inicial devolveu 5 candidatos, **todos** vindos de
`trendpulse-ai-readme.md` - nenhum chunk de `financial-crew-readme.md`
(o documento realmente relevante para esta pergunta) entrou no top-5 do
bi-encoder. O reranking reordenou os 5 candidatos existentes, mas como
nenhum deles e de facto relevante, a reordenacao nao resolve o problema:
continua a nao devolver a resposta certa.

**Observacao importante**: reranking so pode reordenar o que o retrieval
inicial ja trouxe para a mesa - nao substitui um `top_k` demasiado baixo
nem corrige erros de recall do bi-encoder. Se o documento certo nunca
chega ao conjunto candidato, nenhuma quantidade de reranking o vai
recuperar. Isto sugere, para blocos futuros (avaliacao, Bloco 8), medir
recall@k do retriever isoladamente, e nao assumir que reranking "resolve"
problemas de retrieval fraco.

## Nota tecnica sobre os scores

Os scores do cross-encoder (`ms-marco-MiniLM-L-6-v2`) sao logits nao
normalizados, nao probabilidades nem similaridades no intervalo [0, 1] -
podem ser negativos e a magnitude absoluta nao e diretamente comparavel
entre queries diferentes. So a **ordem relativa** dentro do mesmo conjunto
de candidatos e significativa. Isto e relevante para o Bloco 7: o
guardrail de confianca nao pode usar o score do cross-encoder como um
threshold absoluto universal sem calibracao adicional.
