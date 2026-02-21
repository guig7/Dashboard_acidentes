from flask import Flask, render_template, jsonify, request
import pandas as pd
import json

app = Flask(__name__)

# Carrega os dados na inicialização
print("Carregando base de dados...")
csv_path = 'datatran2017-2024.csv'

# Lendo apenas as colunas necessárias para o dashboard para poupar memória e tempo
cols_to_use = [
    'data_inversa', 'uf', 'municipio', 'causa_acidente', 
    'tipo_acidente', 'classificacao_acidente', 'mortos', 'feridos',
    'latitude', 'longitude', 'horario'
]

try:
    # Usando encoding latin-1 e separador ; conforme comum no governo BR e visto no sample
    df = pd.read_csv(csv_path, sep=';', encoding='latin-1', usecols=cols_to_use)
    
    # Conversão de data
    df['data_inversa'] = pd.to_datetime(df['data_inversa'], format='%d/%m/%Y', errors='coerce')
    df['ano'] = df['data_inversa'].dt.year.fillna(0).astype(int)
    df['mes'] = df['data_inversa'].dt.month.fillna(0).astype(int)

    # Limpeza básica em números
    df['mortos'] = pd.to_numeric(df['mortos'], errors='coerce').fillna(0).astype(int)
    df['feridos'] = pd.to_numeric(df['feridos'], errors='coerce').fillna(0).astype(int)

    if 'latitude' in df.columns and 'longitude' in df.columns:
        # Converter coordenadas de string para float (convertendo vírgula para ponto)
        df['latitude'] = pd.to_numeric(
            df['latitude'].astype(str).str.strip().str.replace(',', '.'), 
            errors='coerce'
        )
        df['longitude'] = pd.to_numeric(
            df['longitude'].astype(str).str.strip().str.replace(',', '.'), 
            errors='coerce'
        )
        
        # Filtra valores absolutos com coordenadas válidas (Caixa limítrofe do Brasil)
        df = df[(df['latitude'].between(-35, 6)) & (df['longitude'].between(-75, -34))].dropna(subset=['latitude', 'longitude'])

    print(f"Base carregada com sucesso! {len(df)} registros processados.")
except Exception as e:
    print(f"Erro ao carregar os dados: {e}")
    df = pd.DataFrame()


@app.route('/')
def index():
    return render_template('index.html')

def get_filtered_df():
    df_filtered = df
    if df_filtered.empty:
        return df_filtered
        
    ano = request.args.get('ano')
    uf = request.args.get('uf')
    
    if ano:
        try:
            df_filtered = df_filtered[df_filtered['ano'] == int(ano)]
        except ValueError:
            pass
            
    if uf:
        df_filtered = df_filtered[df_filtered['uf'] == uf.upper()]
        
    return df_filtered


@app.route('/api/stats_gerais')
def stats_gerais():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    total_acidentes = len(df_filtered)
    total_mortos = int(df_filtered['mortos'].sum())
    total_feridos = int(df_filtered['feridos'].sum())
    
    return jsonify({
        'total_acidentes': total_acidentes,
        'total_mortos': total_mortos,
        'total_feridos': total_feridos
    })


@app.route('/api/acidentes_por_ano')
def acidentes_por_ano():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    # Agrupa por ano e conta
    agrupado = df_filtered.groupby('ano').size().reset_index(name='total')
    # Filtra anos invalidos (0 do fillna)
    agrupado = agrupado[agrupado['ano'] > 0]
    
    anos = agrupado['ano'].tolist()
    totais = agrupado['total'].tolist()
    
    return jsonify({
        'labels': anos,
        'data': totais
    })


@app.route('/api/mortos_por_ano')
def mortos_por_ano():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    # Agrupa por ano e soma mortos
    agrupado = df_filtered.groupby('ano')['mortos'].sum().reset_index(name='total')
    agrupado = agrupado[agrupado['ano'] > 0]
    
    anos = agrupado['ano'].tolist()
    totais = agrupado['total'].tolist()
    
    return jsonify({
        'labels': anos,
        'data': [int(x) for x in totais]
    })


@app.route('/api/causas')
def top_causas():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    agrupado = df_filtered['causa_acidente'].value_counts().head(10).reset_index()
    agrupado.columns = ['causa', 'total']
    
    return jsonify({
        'labels': agrupado['causa'].tolist(),
        'data': agrupado['total'].tolist()
    })


@app.route('/api/estados')
def acidentes_ufs():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    agrupado = df_filtered['uf'].value_counts().reset_index()
    agrupado.columns = ['uf', 'total']
    
    return jsonify({
        'labels': agrupado['uf'].tolist(),
        'data': agrupado['total'].tolist()
    })


@app.route('/api/taxa_severidade')
def taxa_severidade():
    # Ano atual e ano anterior
    ano_atual = request.args.get('ano', '')
    
    df_atual = get_filtered_df()
    
    if df_atual.empty:
        return jsonify({})
    
    # Calcular taxa de severidade para ano atual
    total_acidentes_atual = len(df_atual)
    total_mortos_atual = int(df_atual['mortos'].sum())
    
    taxa_severidade_atual = (total_mortos_atual / total_acidentes_atual * 100) if total_acidentes_atual > 0 else 0
    
    # Comparar com ano anterior (se houver)
    taxa_severidade_anterior = 0
    variacao = 0
    
    if ano_atual and ano_atual.isdigit():
        ano_anterior = int(ano_atual) - 1
        df_anterior = df[df['ano'] == ano_anterior]
        
        if not df_anterior.empty:
            total_acidentes_anterior = len(df_anterior)
            total_mortos_anterior = int(df_anterior['mortos'].sum())
            taxa_severidade_anterior = (total_mortos_anterior / total_acidentes_anterior * 100) if total_acidentes_anterior > 0 else 0
            variacao = taxa_severidade_atual - taxa_severidade_anterior
    
    return jsonify({
        'taxa_atual': round(taxa_severidade_atual, 2),
        'taxa_anterior': round(taxa_severidade_anterior, 2),
        'variacao': round(variacao, 2),
        'total_acidentes': total_acidentes_atual,
        'total_mortos': total_mortos_atual
    })


@app.route('/api/heatmap_horarios')
def heatmap_horarios():
    df_filtered = get_filtered_df()
    if df_filtered.empty or 'horario' not in df_filtered.columns:
        return jsonify({})
    
    # Extrair hora do horário (formato HH:MM)
    df_filtered['hora'] = df_filtered['horario'].astype(str).str[:2].apply(lambda x: int(x) if x.isdigit() else 0)
    
    # Agrupar por hora
    agrupado = df_filtered.groupby('hora').agg({
        'mortos': 'sum',
        'horario': 'count'  # count de acidentes
    }).reset_index()
    agrupado.columns = ['hora', 'mortos', 'acidentes']
    agrupado = agrupado.sort_values('hora')
    
    # Calcular severidade por hora
    agrupado['severidade'] = (agrupado['mortos'] / agrupado['acidentes'] * 100).round(2)
    
    return jsonify({
        'labels': [f"{int(h):02d}:00" for h in agrupado['hora']],
        'acidentes': agrupado['acidentes'].tolist(),
        'severidade': agrupado['severidade'].tolist(),
        'mortos': agrupado['mortos'].astype(int).tolist()
    })


@app.route('/api/ranking_estados')
def ranking_estados():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})
    
    # Agrupar por estado 
    agrupado = df_filtered.groupby('uf').agg({
        'mortos': ['sum', 'size']
    })
    
    # Flatten o MultiIndex
    agrupado.columns = ['total_mortos', 'acidentes']
    agrupado = agrupado.reset_index()
    agrupado = agrupado.astype({'total_mortos': 'int', 'acidentes': 'int'})
    
    # Calcular taxa de severidade
    agrupado['taxa_severidade'] = (agrupado['total_mortos'] / agrupado['acidentes'] * 100).round(2)
    
    # Ordenar por taxa de severidade
    agrupado = agrupado.sort_values('taxa_severidade', ascending=False).head(15)
    
    return jsonify({
        'labels': agrupado['uf'].tolist(),
        'taxa_severidade': agrupado['taxa_severidade'].tolist(),
        'acidentes': agrupado['acidentes'].tolist(),
        'mortos': agrupado['total_mortos'].tolist()
    })


@app.route('/api/mapa')
def mapa_acidentes():
    df_filtered = get_filtered_df()
    if df_filtered.empty or 'latitude' not in df_filtered.columns:
        return jsonify([])
    df_map = df_filtered.dropna(subset=['latitude', 'longitude'])
    # Retorna uma amostra de no máximo 100000 pontos para não travar o frontend Leaflet
    if len(df_map) > 100000:
        df_map = df_map.sample(100000)
    coords = df_map[['latitude', 'longitude']].values.tolist()
    return jsonify(coords)


@app.route('/api/tabela_detalhada')
def tabela_detalhada():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify([])
    # Seleciona colunas para a tabela
    cols = ['data_inversa', 'uf', 'municipio', 'causa_acidente', 'tipo_acidente', 'classificacao_acidente', 'mortos', 'feridos', 'horario']
    df_tab = df_filtered[cols].copy()
    # Formata data
    df_tab['data_inversa'] = df_tab['data_inversa'].dt.strftime('%d/%m/%Y')
    # Limita a 500 linhas para performance
    rows = df_tab.head(500).to_dict(orient='records')
    return jsonify(rows)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
