# 🚦 Dashboard de Acidentes de Trânsito — Rodovias Federais BR

> Painel interativo para análise de acidentes nas rodovias federais brasileiras (2017–2024), com visualizações geográficas, rankings de severidade e filtros dinâmicos por ano e estado.

![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)
![Flask](https://img.shields.io/badge/Flask-3.x-black?style=flat-square&logo=flask)
![Pandas](https://img.shields.io/badge/Pandas-2.x-150458?style=flat-square&logo=pandas)
![Chart.js](https://img.shields.io/badge/Chart.js-4.x-FF6384?style=flat-square)
![Leaflet](https://img.shields.io/badge/Leaflet-1.9-199900?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)

---

## 📌 Sobre o Projeto

Este dashboard transforma uma base de dados bruta da PRF (Polícia Rodoviária Federal) em informações visuais e acessíveis, permitindo identificar padrões críticos de segurança viária no Brasil sem precisar manipular arquivos CSV diretamente.

O projeto foi desenvolvido como parte de um portfólio de análise de dados, demonstrando integração entre backend Python, manipulação de dados com Pandas e visualização interativa no frontend.

---

## ✨ Funcionalidades

| Funcionalidade | Descrição |
|---|---|
| 📊 **KPIs em tempo real** | Total de acidentes, mortos, feridos e taxa de severidade com animação de contagem |
| 📈 **Evolução anual** | Gráficos de linha e barra mostrando tendência de acidentes e vítimas fatais |
| 🕐 **Acidentes por hora** | Distribuição horária com sobreposição de taxa de severidade |
| 🏆 **Ranking de estados** | Estados ordenados por taxa de mortalidade, com código de cores por criticidade |
| ⚠️ **Top causas** | As 10 principais causas com gráfico e tabela de severidade por causa |
| 🗺️ **Mapa interativo** | Geolocalização dos acidentes com clusters e popups detalhados por ocorrência |
| 🔍 **Filtros dinâmicos** | Filtro por ano (2017–2024) e estado (todas as UFs) |

---

## 🛠️ Tecnologias

**Backend**
- Python 3.11
- Flask — servidor web e API REST
- Pandas — processamento e agregação dos dados
- KaggleHub — download automático do dataset

**Frontend**
- HTML5 / CSS3 / JavaScript
- Chart.js — gráficos interativos
- Leaflet.js + MarkerCluster — mapa geográfico com clusters
- Google Fonts — Syne, Space Mono, DM Sans

**Dados**
- Fonte: [PRF — Polícia Rodoviária Federal](https://www.gov.br/prf/pt-br)
- Dataset: [`guilherme2008/acidentes-em-rodovias-federais`](https://www.kaggle.com/datasets/guilherme2008/acidentes-em-rodovias-federais) no Kaggle
- Período: 2017 a 2024 (~700 mil registros)

---

## 🚀 Como Rodar

### Pré-requisitos

- Python 3.9+
- Conta no Kaggle com `kaggle.json` configurado ([instruções](https://www.kaggle.com/docs/api))

### Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/guig7/Dashboard_acidentes.git
cd Dashboard_acidentes

# 2. Crie e ative o ambiente virtual
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt
```

### Execução

```bash
python app.py
```

Acesse em: [http://localhost:5000](http://localhost:5000)

> O dataset é baixado automaticamente via KaggleHub na primeira execução. Certifique-se de ter o `kaggle.json` configurado em `~/.kaggle/`.

---

## 📁 Estrutura do Projeto

```
Dashboard_acidentes/
├── app.py                  # Backend Flask + endpoints da API
├── requirements.txt        # Dependências Python
├── static/
│   ├── script.js           # Lógica do frontend (gráficos, mapa, filtros)
│   └── style.css           # Estilos — design system dark mode
├── templates/
│   └── index.html          # Layout principal
└── .gitignore
```

---

## 🔌 API Endpoints

| Endpoint | Descrição |
|---|---|
| `GET /api/stats_gerais` | Total de acidentes, mortos e feridos |
| `GET /api/acidentes_por_ano` | Contagem anual de acidentes |
| `GET /api/mortos_por_ano` | Vítimas fatais por ano |
| `GET /api/taxa_severidade` | Taxa de mortalidade + comparativo com ano anterior |
| `GET /api/heatmap_horarios` | Distribuição por hora do dia |
| `GET /api/ranking_estados` | Estados ordenados por taxa de severidade |
| `GET /api/causas` | Top 10 causas com acidentes, mortos e severidade |
| `GET /api/mapa` | Coordenadas + detalhes de cada acidente (amostra de 100k) |

Todos os endpoints aceitam os parâmetros opcionais `?ano=2023` e `?uf=SP`.

---

## 📊 Exemplos de Insights

- **Finais de semana** concentram os horários de maior severidade (madrugada de sábado e domingo)
- **Estados do Norte e Centro-Oeste** tendem a apresentar maior taxa de mortalidade por acidente
- **Falta de atenção** e **velocidade incompatível** respondem pela maioria dos acidentes registrados

---

## 🤝 Contribuição

Pull requests são bem-vindos! Para sugestões ou melhorias:

1. Fork o projeto
2. Crie sua branch: `git checkout -b feature/minha-melhoria`
3. Commit suas mudanças: `git commit -m 'feat: adiciona nova funcionalidade'`
4. Push para a branch: `git push origin feature/minha-melhoria`
5. Abra um Pull Request

---

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](License) para mais detalhes.

---

<div align="center">
  Desenvolvido por <a href="https://github.com/guig7">guig7</a>
</div>
