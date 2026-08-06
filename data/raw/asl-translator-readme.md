# Tradutor de Língua Gestual em Tempo Real (Alfabeto)

Sistema de tradução automática do alfabeto de Língua Gestual em tempo real, utilizando a webcam do computador. O projeto combina deteção de mãos por **MediaPipe** com um classificador de **Machine Learning tradicional** (Scikit-Learn) para reconhecer letras gestuais de forma leve, rápida e robusta a variações de fundo e iluminação.

## Arquitetura do Sistema

Em vez de treinar uma rede neuronal convolucional (CNN) pesada diretamente sobre imagens em bruto — abordagem que exige grandes volumes de dados, hardware dedicado (GPU) e é sensível a fundo/iluminação/ângulo de câmara — este projeto adota uma estratégia de **duas fases**:

1. **Extração de características (Feature Extraction) com MediaPipe Hands**
   O MediaPipe deteta a mão na imagem e devolve **21 landmarks (pontos-chave)** com coordenadas (x, y) correspondentes às articulações dos dedos e ao pulso. Estes pontos são depois **normalizados** (relativos ao pulso e à escala da mão), tornando a representação invariante à posição da mão no ecrã, à distância à câmara e, em grande medida, ao fundo e à iluminação da cena.

2. **Classificação com Machine Learning tradicional (Scikit-Learn)**
   Em vez de pixels, o classificador (`RandomForestClassifier`) trabalha sobre apenas **42 valores numéricos** (21 landmarks × 2 coordenadas) por amostra. Isto resulta em:
   - Modelos **muito mais pequenos e rápidos** de treinar (segundos/minutos em CPU, sem necessidade de GPU);
   - **Menos dados necessários** para obter boa generalização, comparado com CNNs;
   - Maior **robustez a fundo e iluminação**, já que estes fatores praticamente não afetam a deteção de landmarks do MediaPipe;
   - **Inferência em tempo real** fluida, mesmo em hardware modesto.

Esta separação entre "perceção" (MediaPipe) e "decisão" (Scikit-Learn) simplifica drasticamente o problema face a uma abordagem end-to-end com CNNs.

## Estrutura do Projeto

```
sign-language-translator/
├── requirements.txt
├── README.md
├── data/
│   ├── dataset/
│   │   ├── A/              # Imagens da letra A
│   │   ├── B/              # Imagens da letra B
│   │   └── .../            # Uma subpasta por cada letra do alfabeto
│   └── hand_landmarks.csv  # Gerado por extract_features.py
├── models/
│   └── sign_language_model.p  # Gerado por train_model.py
└── src/
    ├── __init__.py
    ├── extract_features.py     # Extração de landmarks a partir do dataset
    ├── train_model.py          # Treino e avaliação do classificador
    └── inference_webcam.py     # Aplicação em tempo real (webcam)
```

## Como Instalar

### 1. Requisitos prévios
- Python 3.10 ou superior
- Webcam funcional (para a etapa de inferência)

### 2. Criar e ativar um ambiente virtual

```bash
# Criar o ambiente virtual
python3 -m venv venv

# Ativar (Linux/macOS)
source venv/bin/activate

# Ativar (Windows)
venv\Scripts\activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

## Como Usar

O fluxo de trabalho divide-se em três etapas sequenciais: **preparar dados → extrair features → treinar → usar em tempo real**.

### Passo 0 — Preparar o dataset de imagens

Cria a pasta `data/dataset/` com uma subpasta para cada letra do alfabeto que queres reconhecer, contendo várias imagens (`.jpg`, `.png`, etc.) do gesto correspondente:

```
data/dataset/
├── A/
│   ├── img001.jpg
│   ├── img002.jpg
│   └── ...
├── B/
│   ├── img001.jpg
│   └── ...
└── ...
```

> 💡 **Dica:** procura variar o fundo, a iluminação e ligeiramente o ângulo da mão nas imagens de cada letra, para obter um modelo mais robusto — mesmo sendo um classificador leve, a qualidade dos dados de treino continua a ser o fator mais importante.

### Passo 1 — Extrair os landmarks das imagens

```bash
python src/extract_features.py
```

Este script:
- Percorre todas as imagens em `data/dataset/<LETRA>/`;
- Deteta a mão e extrai os 21 landmarks com o MediaPipe;
- Normaliza as coordenadas;
- Guarda tudo em `data/hand_landmarks.csv`;
- Regista no terminal quantas imagens foram processadas com sucesso e quantas foram ignoradas (por não ter mão detetada ou por erro de leitura).

### Passo 2 — Treinar o classificador

```bash
python src/train_model.py
```

Este script:
- Carrega `data/hand_landmarks.csv`;
- Divide os dados em treino (80%) e teste (20%), de forma estratificada por classe;
- Treina um `RandomForestClassifier`;
- Imprime a **Accuracy** e o **Classification Report** (precision, recall, f1-score por letra);
- Guarda o modelo treinado em `models/sign_language_model.p`.

### Passo 3 — Executar a tradução em tempo real

```bash
python src/inference_webcam.py
```

Este script:
- Abre a webcam (índice 0 por omissão);
- Deteta a mão em tempo real com o MediaPipe;
- Desenha o esqueleto da mão sobre o vídeo;
- Classifica o gesto atual com o modelo treinado;
- Mostra a letra prevista (e a confiança da previsão) sobre a imagem, com fundo sólido para garantir boa visibilidade.

Pressiona **`q`** na janela de vídeo para sair.

## Melhorias Futuras

- **Reconhecimento de frases (sequências de texto):** em vez de classificar apenas letras isoladas, integrar um modelo sequencial (LSTM, GRU ou um pequeno Transformer) que analise a evolução dos landmarks ao longo do tempo, permitindo compor palavras e frases completas.
- **Suporte a gestos dinâmicos:** muitas línguas gestuais (incluindo palavras completas, não apenas o alfabeto datilológico) dependem de movimento e não apenas da pose estática da mão; isto implicaria capturar sequências de frames (janelas temporais) em vez de imagens isoladas.
- **Suporte a duas mãos:** alguns gestos e línguas gestuais completas requerem a deteção e combinação simultânea de ambas as mãos.
- **Deteção de expressões faciais e postura:** em línguas gestuais completas, elementos não-manuais (expressão facial, movimento da cabeça/ombros) também transmitem significado gramatical.
- **Interface gráfica dedicada:** substituir a janela simples do OpenCV por uma interface mais amigável (ex: Streamlit ou PyQt), com histórico de letras reconhecidas e composição de palavras.
- **Validação cruzada e ajuste de hiperparâmetros:** usar `GridSearchCV`/`RandomizedSearchCV` para otimizar os hiperparâmetros do classificador e comparar diferentes algoritmos (SVM, XGBoost, redes neuronais simples sobre os landmarks).
