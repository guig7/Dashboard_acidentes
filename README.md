# Dashboard de Acidentes de Trânsito — Rodovias Federais BR

Painel interativo para análise de acidentes em rodovias federais brasileiras (2017–2024), preparado para rodar em Cloudflare Workers no endereço `*.workers.dev`.

## Como funciona nesta versão

O Worker serve a interface estática e a API Flask. Para manter a inicialização leve e evitar baixar centenas de milhares de registros em cada execução, a base é pré-processada fora da Cloudflare em arquivos JSON compactos, organizados pelos filtros de ano e UF. O mapa retorna amostras limitadas: 2.000 ocorrências sem filtro e até 500 por combinação filtrada.

A rotina de geração usa o CSV do dataset Kaggle `guilherme2008/acidentes-em-rodovias-federais`. O CSV bruto não é incluído no Git; os JSONs derivados ficam em `public/data/` e precisam ser versionados para o Worker os servir.

## Pré-requisitos

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js/npm (Wrangler é usado pelo PyWrangler)
- Credenciais Kaggle configuradas em `~/.kaggle/kaggle.json`, ou o CSV baixado manualmente
- Conta Cloudflare para publicar o Worker

## 1. Gerar os dados do dashboard

Instale as dependências da etapa de pré-processamento:

```bash
python -m pip install -r requirements-data.txt
```

Com credenciais Kaggle configuradas:

```bash
python tools/build_data.py
```

Ou informe o caminho para o CSV já baixado:

```bash
python tools/build_data.py --csv caminho/para/datatran2017-2024.csv
```

A rotina cria `public/data/summary.json`, além de arquivos de mapa e tabela em `public/data/maps/` e `public/data/tables/`. Também prepara os trajetos oficiais das BRs em `public/data/roads/all.geojson` e os acidentes por rodovia em `public/data/roads/accidents/`.

O gerador consulta a camada de rodovias federais do DNIT publicada pela Infra S.A. (SNV 202501A), então precisa de acesso à internet. `--skip-roads` deixa as geometrias existentes sem atualização.

## 2. Rodar localmente

Instale o ambiente do Worker e inicie o servidor de desenvolvimento da Cloudflare:

```bash
uv sync
uv run pywrangler dev
```

Abra o endereço local informado pelo Wrangler, normalmente `http://localhost:8787`.

## 3. Publicar em `workers.dev`

Publique o Worker; na primeira execução, o Wrangler solicitará autenticação e associação à sua conta:

```bash
uv run pywrangler deploy
```

O primeiro deploy permite associar a conta e habilitar o subdomínio `workers.dev`. O nome configurado é `dashboard-acidentes-prf`; se já estiver ocupado, altere `name` em `wrangler.jsonc` antes do deploy.

## Rotas da API

Os endpoints mantêm os nomes usados pelo dashboard e aceitam `?ano=2023` e `?uf=SP`:

- `GET /api/stats_gerais`
- `GET /api/acidentes_por_ano`
- `GET /api/mortos_por_ano`
- `GET /api/taxa_severidade`
- `GET /api/heatmap_horarios`
- `GET /api/ranking_estados`
- `GET /api/causas`
- `GET /api/estados`
- `GET /api/mapa`
- `GET /api/tabela_detalhada`

No mapa, clique em uma linha ou escolha uma BR no seletor para destacar o trajeto e ver os acidentes geolocalizados nessa rodovia. Ano e estado refinam os pontos. O filtro BR afeta apenas o mapa; os demais indicadores continuam agregados por ano e estado.

## Atualizar a base

Baixe a versão atualizada do CSV e rode novamente `python tools/build_data.py --csv ...`. Confira e versione os arquivos novos em `public/data/roads/` junto dos dados existentes. Depois, publique a nova versão com `uv run pywrangler deploy`.

Fonte das geometrias: [DNIT/Infra S.A. — Rodovias Federais (SNV 202501A)](https://geo.infrasa.gov.br/server/rest/services/Hosted/Rodovias_Federais/FeatureServer/0).

> Os arquivos em `public/data/` precisam existir antes do deploy. Sem eles, o Worker retorna HTTP 503 nas rotas de dados.

## Tecnologias

- Python 3.12, Flask e Cloudflare Python Workers
- Wrangler/PyWrangler e Workers Static Assets
- Pandas e KaggleHub na etapa de pré-processamento
- Chart.js e Leaflet no frontend

## Licença

MIT. Consulte [License](License).
