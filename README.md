# Dashboard de Acidentes de Trânsito - Detran Brasil

Este projeto é um painel interativo para análise de acidentes de trânsito no Brasil, utilizando dados do Detran de 2017 a 2024. O dashboard permite visualizar estatísticas, tendências, mapas e rankings de severidade, facilitando a tomada de decisões e a identificação de pontos críticos.

## Funcionalidades

- **KPIs Principais:** Total de acidentes, mortos, feridos e taxa de severidade.
- **Gráficos Interativos:** Evolução anual de acidentes e vítimas fatais, acidentes por hora do dia, principais causas, ranking de estados.
- **Mapa Geográfico:** Visualização dos acidentes por localização, com clusters.
- **Filtros Dinâmicos:** Por ano e estado.
- **Layout Moderno:** Interface responsiva, dark mode, visualização clara e hierárquica.

## Tecnologias Utilizadas

- **Backend:** Python 3.11, Flask, Pandas
- **Frontend:** HTML5, CSS3, JavaScript, Chart.js, Leaflet.js
- **Dados:** Arquivo CSV `datatran2017-2024.csv` (não incluído por padrão)

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/guig7/Dashboard_acidentes.git
   cd Dashboard_acidentes
   ```
2. Crie um ambiente virtual:
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # ou
   source venv/bin/activate  # Linux/Mac
   ```
3. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```
4. Adicione o arquivo de dados `datatran2017-2024.csv` na raiz do projeto.

## Execução

1. Inicie o servidor Flask:
   ```bash
   python app.py
   ```
2. Acesse o dashboard em [http://localhost:5000](http://localhost:5000)

## Estrutura do Projeto

```
├── app.py                # Backend Flask
├── requirements.txt      # Dependências Python
├── static/
│   ├── script.js         # Lógica frontend
│   └── style.css         # Estilos
├── templates/
│   └── index.html        # Layout principal
├── datatran2017-2024.csv # Dados (não incluído)
└── .gitignore            # Ignora arquivos sensíveis
```

## Contribuição

Pull requests são bem-vindos! Para sugestões, melhorias ou correções, abra uma issue ou envie um PR.

## Licença

Este projeto está sob a licença MIT.

---

**Autor:** [guig7](https://github.com/guig7)
