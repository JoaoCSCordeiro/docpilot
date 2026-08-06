# Comparacao de estrategias de chunking

Resultados obtidos correndo `src/evaluation/chunking_comparison.py` sobre o
corpus atual em `data/raw` (5 documentos carregados por `load_documents`,
que so aceita `.md` e `.txt` - o ficheiro `django-readme.rst` fica de fora
por ter extensao `.rst`):

- `asl-translator-readme.md` (6339 caracteres)
- `financial-crew-readme.md` (19470 caracteres)
- `trendpulse-ai-readme.md` (22390 caracteres)
- `external/FastAPI-readme.md` (22923 caracteres)
- `external/psfrequests-readme.md` (2894 caracteres)

Parametros usados (mesmo tamanho-alvo para as duas estrategias, para a
comparacao ser justa):

- Fixed-size: `chunk_size=500`, `overlap=50`
- Semantic: `max_chunk_size=500`, `overlap_sentences=1`

## Resultados

| strategy   | num_chunks | mean_size | variance | min_size | max_size |
|------------|-----------:|----------:|---------:|---------:|---------:|
| fixed-size |        167 |     491.6 |   2817.7 |       39 |      500 |
| semantic   |        242 |     485.8 |  53654.4 |       10 |     1857 |

## Interpretacao

- **Tamanho medio**: as duas estrategias ficam perto do alvo de 500
  caracteres (491.6 vs 485.8), o que era esperado dado que ambas usam o
  mesmo `max_chunk_size`/`chunk_size`.

- **Numero de chunks**: o semantic gera mais chunks (242 vs 167), porque
  nunca junta paragrafos/frases alem do limite - prefere um chunk mais
  pequeno a cortar uma frase a meio, enquanto o fixed-size aproveita
  sempre o espaco ate ao limite exato.

- **Variancia**: e aqui que a diferenca e mais visivel. O fixed-size tem
  variancia baixa (2817.7) porque quase todos os chunks ficam com
  exatamente 500 caracteres, exceto o ultimo chunk de cada documento.
  O semantic tem variancia quase 19x maior (53654.4), com 63 chunks acima
  de 500 caracteres e 12 acima de 1000.

- **Causa dos outliers no semantic**: o maior chunk (1857 caracteres, em
  `external/FastAPI-readme.md`) e um bloco de badges/links HTML de
  patrocinadores, escrito numa unica linha sem pontuacao de fim de frase
  (`. ! ?`) nem separacao por linha em branco. Como o splitter semantico
  so corta em fronteiras de paragrafo ou de frase, e nunca a meio de uma
  unidade, este bloco fica inteiro num so chunk, muito acima do limite de
  500. O mesmo padrao (paragrafos longos sem pontuacao - normalmente
  blocos de markup, tabelas ou listas de links) explica os outros
  outliers em `financial-crew-readme.md` e `trendpulse-ai-readme.md`.

## Conclusao

Nenhuma das duas estrategias e estritamente melhor - representam um
trade-off:

- **Fixed-size** garante um tamanho de chunk previsivel (util para
  controlar custos de embedding/tokens), mas corta frases e paragrafos a
  meio, o que pode partir o contexto semantico de uma ideia entre dois
  chunks.
- **Semantic** preserva sempre a integridade de frases e paragrafos, mas
  nao da nenhuma garantia de tamanho maximo - documentos com blocos de
  texto densos e sem pontuacao (HTML, tabelas, listas de links) produzem
  chunks muito maiores que o alvo.

Para o retrieval (Bloco 4 em diante), o fixed-size e a escolha mais segura
por defeito, dado o controlo de tamanho. O semantic fica documentado como
alternativa e pode ser revisitado se a qualidade do retrieval mostrar
perda de contexto nas fronteiras dos chunks fixed-size.
