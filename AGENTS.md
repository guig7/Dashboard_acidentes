# Contexto do projeto para assistentes de IA

Leia este arquivo e o `README.md` antes de propor ou alterar o projeto. Converse com o usuário em português do Brasil. Preserve as decisões e funcionalidades descritas aqui; confirme o código atual antes de assumir que uma ideia já está implementada.

## Objetivo e público

O projeto é um dashboard interativo de acidentes em rodovias federais brasileiras, baseado em registros da PRF de 2017 a 2024. O foco é permitir exploração visual por ano, UF e rodovia, sem apresentar os dados como prova de causalidade ou como medida de risco sem denominador de exposição ao tráfego.

- Site publicado: https://dashboard-acidentes-prf.guisoaresg7.workers.dev/
- Repositório: https://github.com/guig7/Dashboard_acidentes
- Licença: MIT.

## Arquitetura atual

- A aplicação é servida pelo Cloudflare Workers, com um Worker Python/Flask para rotas `/api/*` e Workers Static Assets para a interface e arquivos preparados em `public/`.
- O Worker lê JSON/GeoJSON por meio do binding `ASSETS`; ele não carrega nem processa o CSV bruto em cada acesso.
- `tools/build_data.py` prepara os dados antes da publicação. As fontes incluem o dataset PRF no Kaggle, geometrias de rodovias do DNIT/Infra S.A. e limites geográficos do IBGE.
- Os JSONs de `public/data/` são recursos públicos necessários ao site. Nunca colocar segredos ou dados privados nessa pasta.

## Experiência existente

- Filtros globais: ano e UF; atualizam indicadores, gráficos, tabela e ocorrências do mapa.
- Filtro de BR: atua no mapa, destaca o trecho selecionado e filtra os acidentes daquela rodovia.
- Mapa vetorial próprio do Brasil, com limites de estados e traçados de rodovias, sem tiles de mapa externo.
- Modos de acidentes: pontos, calor e ocultar.
- API inclui resumos, séries, severidade, horários, ranking, causas, estados, mapa e tabela detalhada. Confira `src/worker.py` para a implementação exata dos endpoints.

## Arquivos que precisam permanecer sincronizados

- Interface fonte e publicada: `templates/index.html` ↔ `public/index.html`.
- JavaScript fonte e publicado: `static/script.js` ↔ `public/static/script.js`.
- CSS fonte e publicado: `static/style.css` ↔ `public/static/style.css`.

Ao alterar um desses pares, aplicar a mesma mudança às duas cópias. O Wrangler publica `public/`, não as pastas de origem `templates/` e `static/`.

## Filtros e mapa: detalhes importantes

- `static/script.js` gerencia o mapa, os filtros e o carregamento das geometrias.
- O mapa usa uma sequência de requisição para ignorar respostas antigas quando filtros mudam rapidamente. Os filtros macro são agrupados por um debounce curto.
- Os arquivos geográficos usam cache de promessas em andamento, para evitar downloads duplicados durante trocas rápidas. Respostas têm timeout e erros devem aparecer no status do mapa, sem deixar dados antigos parecerem atuais.
- Ao mudar UF/BR, remover ou atualizar a camada rodoviária anterior. Reenquadrar o mapa para o Brasil ou a UF filtrada quando apropriado.
- Valores padrão do pré-processamento limitam pontos para manter a interface responsiva: até 2.000 no mapa geral, 500 em mapas com filtros macro e até 2.500 quando uma BR é selecionada. O total do recorte e a amostra exibida não são a mesma coisa; não descrever os pontos desenhados como todos os acidentes quando há limite.
- Se mexer no fluxo do mapa, comparar os arquivos `static/script.js` e `public/static/script.js` e validar que continuam idênticos.

## Ideia de IA discutida, ainda não implementada

Foi considerada uma evolução para um analista de dados por linguagem natural. Trate isso como proposta, não como funcionalidade existente nem como autorização para implementá-la automaticamente.

Direção recomendada se o usuário pedir para construir:

1. O modelo interpreta a pergunta e escolhe entre ferramentas de domínio previamente definidas, como consultar totais, comparar UFs, listar causas ou obter séries.
2. O Worker valida ano, UF, métrica e limites, e executa os cálculos com a API/dados estruturados. Não aceitar SQL arbitrário produzido pelo modelo.
3. O modelo redige uma explicação somente a partir dos resultados retornados, citando o recorte e a fonte e admitindo quando a pergunta não pode ser respondida.
4. Criar perguntas de referência e avaliar seleção de ferramenta, extração dos filtros, fidelidade numérica, citações, recusas adequadas, latência e consumo.
5. Workers AI pode fornecer inferência; AI Gateway pode apoiar observabilidade. D1 só é necessário se as consultas estruturadas pedirem acesso mais flexível do que os JSONs atuais. RAG/Vectorize é mais apropriado para documentos de metodologia e definições do que para obter totais numéricos.

Não adicionar D1, Vectorize, AI Gateway ou outros serviços pagos/novos sem explicar a necessidade, os recursos que precisam ser habilitados e possíveis limites/custos ao usuário.

## Preferências de trabalho

- Fazer mudanças pequenas, coerentes com a arquitetura atual e com a identidade visual existente.
- Não alterar, regenerar ou remover grandes arquivos de `public/data/` sem verificar o impacto e o pedido do usuário.
- Não inventar métricas, previsões ou afirmações sobre gravidade/risco. Separar fatos da base, amostras e inferências.
- O README deve explicar o projeto e apontar para o site; o usuário pediu que ele não traga instruções para execução local.
- Antes de sincronizar mudanças com o GitHub, verificar a branch e o estado do repositório e relatar com precisão o que foi publicado.

