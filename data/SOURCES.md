# Fontes do corpus

Ficheiros copiados neste ambiente (2026-08-06):

- `financial-crew-readme.md` - README do projeto Financial Crew
- `asl-translator-readme.md` - README do projeto ASL Translator
  (sign-language-translator)
- `trendpulse-ai-readme.md` - README do projeto TrendPulse AI

## Projetos em falta

Os seguintes projetos fazem parte dos 6 referidos em
`docs/plano-blocos.md`, mas nao tinham um README acessivel neste
ambiente:

- TravelMaster AI - pasta existe
  (`Projetos/TravelMaster_AI`), mas nao tem `README.md`.
- AI-Powered Health Assistant - pasta nao encontrada em `Projetos/`.
- Secure Parking Management System - pasta nao encontrada em `Projetos/`.

Para completar o corpus, copiar manualmente a documentacao destes
projetos para `data/raw/` (formato `.md` ou `.txt`) quando estiver
disponivel.

## Documentos envenenados para avaliacao (Bloco 18)

`data/evaluation/poisoned/` contem tres documentos sinteticos, escritos para
o eval de prompt injection indireto (`orbit-scheduler-readme.md`,
`projeto-lince-cache.md`, `fastapi-deployment-notes.md`). Descrevem projetos
ficticios e contem instrucoes escondidas com a string canario
`DOCPILOT-CANARY-7Q2X`. Ficam fora de `data/raw` de proposito: o loader le
`data/raw` recursivamente e nunca os deve indexar na coleccao principal; o
`scripts/run_llm_evaluation.py` indexa-os so na coleccao
`docpilot_eval_injection`.
