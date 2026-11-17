# Contexto do projeto para assistentes de IA

Leia este arquivo e o README.md antes de alterar o projeto. Converse em português do Brasil. O código no GitHub/main já inclui um analista com Workers AI; não descreva esse recurso como apenas planejado. Confirme sempre a implementação e o estado atual da branch antes de editar.

## Produto

Dashboard interativo de acidentes em rodovias federais do Brasil, com registros PRF 2017–2024. Permite análise descritiva por ano, UF, rodovia, horário, clima, causa e outras dimensões.

- Site: https://dashboard-acidentes-prf.guisoaresg7.workers.dev/
- Repositório: https://github.com/guig7/Dashboard_acidentes
- Licença MIT.

Não afirmar causalidade, previsão de acidentes ou risco por rodovia/grupo sem dados de exposição ao tráfego. O mapa pode exibir amostras limitadas, não todos os registros.

## Arquitetura

- Cloudflare Worker Python/Flask em src/worker.py processa /api/* e lê Static Assets pelo binding ASSETS.
- A interface estática e os JSON/GeoJSON públicos são servidos de public/.
- tools/build_data.py lê e valida o CSV fora das requisições do site e gera summary, analytics, partitions de registros, mapas, tabelas e recursos geográficos.
- public/data/ é público; não inserir segredos ou dados privados.
- Fontes principais: dataset PRF/Kaggle, geometrias DNIT/Infra S.A., limites IBGE.

## Funcionalidades

- Filtros globais ano e UF atualizam indicadores, gráficos, distribuições, tabela de registros e ocorrências no mapa.
- O seletor de BR é independente e afeta apenas o traçado e os acidentes exibidos no mapa.
- Mapa vetorial próprio com modos pontos, calor e ocultar.
- Distribuições categóricas paginadas, registros completos paginados, preservando os 30 campos da fonte.
- API adicional para consultas determinísticas e perguntas em português via Workers AI.

## Analista IA já implementado

- Endpoints em src/worker.py: POST /api/analista/consulta (consultas determinísticas), GET /api/analista/status, POST /api/analista/perguntar (Workers AI + ferramentas controladas).
- Implementação de planejamento/síntese: src/analyst_ai.py. Consultas validadas: src/analyst_queries.py. Registros e análises detalhadas: src/record_queries.py. Esquema comum: src/data_schema.py.
- Modelo configurado: @cf/zai-org/glm-4.7-flash, binding AI em wrangler.jsonc e variável ANALYST_AI_ENABLED.
- O modelo planeja chamadas a ferramentas de domínio; o Worker valida argumentos e executa consultas contra JSONs preparados. Não executar SQL ou Python arbitrário gerado pelo modelo, nem dar acesso do modelo à base inteira.
- Limites atuais descritos no README e no código: texto da pergunta, chamadas por plano, chamadas detalhadas, escopo de registros, comprimento da resposta e rate limit por IP.
- Respostas devem distinguir registros observados de causalidade ou risco, trazer filtros/fontes e recusar perguntas não suportadas, como previsão futura ou risco sem denominador de exposição.
- Workers Observability está configurado. AI Gateway, armazenamento próprio de conversas e orçamento global rígido de tokens/custo não estão implementados.
- Avaliação do analista deve usar perguntas de referência com ferramenta/filtros/resultados esperados; medir extração de filtros, fidelidade numérica, citações, recusas, latência e consumo. Não alegar métricas de qualidade não medidas.
- RAG/Vectorize pode servir documentos de metodologia, não substituir consultas estruturadas para totais.

## Arquivos sincronizados e dados

- templates/index.html ↔ public/index.html.
- static/script.js ↔ public/static/script.js.
- static/style.css ↔ public/static/style.css.
- Manter cópias pareadas sincronizadas; Wrangler publica public/.
- Não regerar/remover grandes recursos em public/data sem conferir impacto.
- Os limites padrão de amostragem do mapa estão em tools/build_data.py e descritos no README. Totais de resumos e pontos visíveis são conceitos diferentes.

## Preferências

- Fazer mudanças pequenas e compatíveis com a identidade visual atual.
- O README deve explicar o projeto, incluir link do site e não ensinar a rodar localmente.
- Antes de publicar no GitHub, verificar a branch/estado e relatar com precisão o que foi enviado.
