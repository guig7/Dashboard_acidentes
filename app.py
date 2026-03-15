from flask import Flask, render_template, jsonify, request
import pandas as pd
import json

import os
import pandas as pd
import kagglehub

path = kagglehub.dataset_download("guilherme2008/acidentes-em-rodovias-federais")

csv_file = os.path.join(path, "datatran2017-2024.csv")


app = Flask(__name__)

# Carrega os dados na inicialização
print("Carregando base de dados...")
csv_path = csv_file

cols_to_use = [
    'data_inversa', 'uf', 'municipio', 'causa_acidente',
    'tipo_acidente', 'classificacao_acidente', 'mortos', 'feridos',
    'latitude', 'longitude', 'horario'
]

try:
    df = pd.read_csv(csv_path, sep=';', encoding='latin-1', usecols=cols_to_use)

    df['data_inversa'] = pd.to_datetime(df['data_inversa'], format='%d/%m/%Y', errors='coerce')
    df['ano'] = df['data_inversa'].dt.year.fillna(0).astype(int)
    df['mes'] = df['data_inversa'].dt.month.fillna(0).astype(int)

    df['mortos'] = pd.to_numeric(df['mortos'], errors='coerce').fillna(0).astype(int)
    df['feridos'] = pd.to_numeric(df['feridos'], errors='coerce').fillna(0).astype(int)

    if 'latitude' in df.columns and 'longitude' in df.columns:
        df['latitude'] = pd.to_numeric(
            df['latitude'].astype(str).str.strip().str.replace(',', '.'),
            errors='coerce'
        )
        df['longitude'] = pd.to_numeric(
            df['longitude'].astype(str).str.strip().str.replace(',', '.'),
            errors='coerce'
        )
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
    uf  = request.args.get('uf')

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

    return jsonify({
        'total_acidentes': len(df_filtered),
        'total_mortos':    int(df_filtered['mortos'].sum()),
        'total_feridos':   int(df_filtered['feridos'].sum())
    })


@app.route('/api/acidentes_por_ano')
def acidentes_por_ano():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})

    agrupado = df_filtered.groupby('ano').size().reset_index(name='total')
    agrupado = agrupado[agrupado['ano'] > 0]

    return jsonify({'labels': agrupado['ano'].tolist(), 'data': agrupado['total'].tolist()})


@app.route('/api/mortos_por_ano')
def mortos_por_ano():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})

    agrupado = df_filtered.groupby('ano')['mortos'].sum().reset_index(name='total')
    agrupado = agrupado[agrupado['ano'] > 0]

    return jsonify({'labels': agrupado['ano'].tolist(), 'data': [int(x) for x in agrupado['total'].tolist()]})


@app.route('/api/causas')
def top_causas():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})

    # Top 10 causas com total de acidentes, mortos e feridos
    agrupado = df_filtered.groupby('causa_acidente').agg(
        total=('causa_acidente', 'count'),
        mortos=('mortos', 'sum'),
        feridos=('feridos', 'sum')
    ).reset_index()

    agrupado = agrupado.sort_values('total', ascending=False).head(10)
    agrupado['taxa_severidade'] = (agrupado['mortos'] / agrupado['total'] * 100).round(2)

    return jsonify({
        'labels':          agrupado['causa_acidente'].tolist(),
        'data':            agrupado['total'].tolist(),
        'mortos':          agrupado['mortos'].astype(int).tolist(),
        'feridos':         agrupado['feridos'].astype(int).tolist(),
        'taxa_severidade': agrupado['taxa_severidade'].tolist()
    })


@app.route('/api/estados')
def acidentes_ufs():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})

    agrupado = df_filtered['uf'].value_counts().reset_index()
    agrupado.columns = ['uf', 'total']

    return jsonify({'labels': agrupado['uf'].tolist(), 'data': agrupado['total'].tolist()})


@app.route('/api/taxa_severidade')
def taxa_severidade():
    ano_atual  = request.args.get('ano', '')
    df_atual   = get_filtered_df()

    if df_atual.empty:
        return jsonify({})

    total_acidentes_atual = len(df_atual)
    total_mortos_atual    = int(df_atual['mortos'].sum())
    taxa_atual            = (total_mortos_atual / total_acidentes_atual * 100) if total_acidentes_atual > 0 else 0

    taxa_anterior = 0
    variacao      = 0

    if ano_atual and ano_atual.isdigit():
        ano_ant    = int(ano_atual) - 1
        df_ant     = df[df['ano'] == ano_ant]
        if not df_ant.empty:
            t_acid    = len(df_ant)
            t_mort    = int(df_ant['mortos'].sum())
            taxa_anterior = (t_mort / t_acid * 100) if t_acid > 0 else 0
            variacao      = taxa_atual - taxa_anterior

    return jsonify({
        'taxa_atual':      round(taxa_atual, 2),
        'taxa_anterior':   round(taxa_anterior, 2),
        'variacao':        round(variacao, 2),
        'total_acidentes': total_acidentes_atual,
        'total_mortos':    total_mortos_atual
    })


@app.route('/api/heatmap_horarios')
def heatmap_horarios():
    df_filtered = get_filtered_df()
    if df_filtered.empty or 'horario' not in df_filtered.columns:
        return jsonify({})

    df_filtered = df_filtered.copy()
    df_filtered['hora'] = df_filtered['horario'].astype(str).str[:2].apply(lambda x: int(x) if x.isdigit() else 0)

    agrupado = df_filtered.groupby('hora').agg(
        mortos=('mortos', 'sum'),
        acidentes=('horario', 'count')
    ).reset_index()
    agrupado = agrupado.sort_values('hora')
    agrupado['severidade'] = (agrupado['mortos'] / agrupado['acidentes'] * 100).round(2)

    return jsonify({
        'labels':    [f"{int(h):02d}:00" for h in agrupado['hora']],
        'acidentes': agrupado['acidentes'].tolist(),
        'severidade':agrupado['severidade'].tolist(),
        'mortos':    agrupado['mortos'].astype(int).tolist()
    })


@app.route('/api/ranking_estados')
def ranking_estados():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify({})

    agrupado = df_filtered.groupby('uf').agg(
        total_mortos=('mortos', 'sum'),
        acidentes=('mortos', 'size')
    ).reset_index()
    agrupado = agrupado.astype({'total_mortos': 'int', 'acidentes': 'int'})
    agrupado['taxa_severidade'] = (agrupado['total_mortos'] / agrupado['acidentes'] * 100).round(2)
    agrupado = agrupado.sort_values('taxa_severidade', ascending=False).head(15)

    return jsonify({
        'labels':          agrupado['uf'].tolist(),
        'taxa_severidade': agrupado['taxa_severidade'].tolist(),
        'acidentes':       agrupado['acidentes'].tolist(),
        'mortos':          agrupado['total_mortos'].tolist()
    })


@app.route('/api/mapa')
def mapa_acidentes():
    df_filtered = get_filtered_df()
    if df_filtered.empty or 'latitude' not in df_filtered.columns:
        return jsonify([])

    df_map = df_filtered.dropna(subset=['latitude', 'longitude']).copy()

    if len(df_map) > 100000:
        df_map = df_map.sample(100000, random_state=42)

    # Formata data para string legível
    df_map['data_fmt'] = df_map['data_inversa'].dt.strftime('%d/%m/%Y').fillna('—')

    registros = df_map[[
        'latitude', 'longitude',
        'municipio', 'uf',
        'causa_acidente', 'classificacao_acidente',
        'mortos', 'feridos',
        'data_fmt', 'horario'
    ]].rename(columns={'data_fmt': 'data'})

    # Preenche NaN com string vazia para JSON limpo
    registros = registros.fillna('—')

    return jsonify(registros.to_dict(orient='records'))


@app.route('/api/tabela_detalhada')
def tabela_detalhada():
    df_filtered = get_filtered_df()
    if df_filtered.empty:
        return jsonify([])

    cols = ['data_inversa', 'uf', 'municipio', 'causa_acidente',
            'tipo_acidente', 'classificacao_acidente', 'mortos', 'feridos', 'horario']
    df_tab = df_filtered[cols].copy()
    df_tab['data_inversa'] = df_tab['data_inversa'].dt.strftime('%d/%m/%Y')
    return jsonify(df_tab.head(500).to_dict(orient='records'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
