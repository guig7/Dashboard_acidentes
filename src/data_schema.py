"""Shared schema for prepared PRF records and deterministic aggregates."""

RECORD_COLUMNS = (
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km", "municipio",
    "causa_acidente", "tipo_acidente", "classificacao_acidente", "fase_dia",
    "sentido_via", "condicao_metereologica", "tipo_pista", "tracado_via", "uso_solo",
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos", "ignorados",
    "feridos", "veiculos", "latitude", "longitude", "regional", "delegacia", "uop",
)

ANALYTIC_DIMENSIONS = {
    "ano": "Ano",
    "mes": "Mês",
    "dia_semana": "Dia da semana",
    "fase_dia": "Fase do dia",
    "sentido_via": "Sentido da via",
    "condicao_metereologica": "Condição meteorológica",
    "tipo_pista": "Tipo de pista",
    "tracado_via": "Traçado da via",
    "uso_solo": "Uso do solo",
    "causa_acidente": "Causa registrada",
    "tipo_acidente": "Tipo de acidente",
    "classificacao_acidente": "Classificação do acidente",
    "uf": "UF",
    "br": "BR",
    "municipio": "Município",
    "regional": "Regional",
    "delegacia": "Delegacia",
    "uop": "Unidade operacional",
    "hora": "Hora do dia",
}

ANALYTIC_METRICS = (
    "acidentes", "mortos", "feridos", "feridos_leves", "feridos_graves",
    "pessoas", "ilesos", "ignorados", "veiculos",
)

RECORD_INTEGER_FIELDS = frozenset({
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
    "ignorados", "feridos", "veiculos",
})

RECORD_FLOAT_FIELDS = frozenset({"km", "latitude", "longitude"})
