"""Shared schema for prepared PRF records and deterministic aggregates."""

RECORD_COLUMNS = (
    "id", "data_inversa", "dia_semana", "horario", "uf", "br", "km", "municipio",
    "causa_acidente", "tipo_acidente", "classificacao_acidente", "fase_dia",
    "sentido_via", "condicao_metereologica", "tipo_pista", "tracado_via", "uso_solo",
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos", "ignorados",
    "feridos", "veiculos", "latitude", "longitude", "regional", "delegacia", "uop",
)

RECORD_FIELD_DESCRIPTIONS = {
    "id": "Identificador do registro.",
    "data_inversa": "Data registrada no formato DD/MM/AAAA.",
    "dia_semana": "Dia da semana registrado.",
    "horario": "Horário registrado.",
    "uf": "Sigla da unidade federativa.",
    "br": "Número da rodovia, armazenado sem o prefixo BR.",
    "km": "Quilômetro registrado da rodovia.",
    "municipio": "Município registrado.",
    "causa_acidente": "Causa registrada no conjunto de dados.",
    "tipo_acidente": "Tipo de acidente registrado.",
    "classificacao_acidente": "Classificação registrada do acidente.",
    "fase_dia": "Fase do dia registrada.",
    "sentido_via": "Sentido da via registrado.",
    "condicao_metereologica": "Condição meteorológica registrada.",
    "tipo_pista": "Tipo de pista registrado.",
    "tracado_via": "Traçado da via registrado.",
    "uso_solo": "Uso do solo registrado.",
    "pessoas": "Pessoas envolvidas no acidente.",
    "mortos": "Mortos registrados no acidente.",
    "feridos_leves": "Feridos leves registrados no acidente.",
    "feridos_graves": "Feridos graves registrados no acidente.",
    "ilesos": "Pessoas ilesas registradas no acidente.",
    "ignorados": "Pessoas com estado físico ignorado.",
    "feridos": "Total de feridos registrados no acidente.",
    "veiculos": "Veículos envolvidos no acidente.",
    "latitude": "Latitude registrada, quando disponível.",
    "longitude": "Longitude registrada, quando disponível.",
    "regional": "Regional da PRF registrada.",
    "delegacia": "Delegacia da PRF registrada.",
    "uop": "Unidade operacional da PRF registrada.",
    "ano": "Ano derivado da data; datas inválidas não têm ano.",
    "mes": "Mês derivado da data, de 01 a 12.",
    "hora": "Faixa horária derivada do horário, no formato HH:00.",
}

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

RECORD_FILTER_FIELDS = (
    frozenset(RECORD_COLUMNS) - {"uf"}
) | {"mes", "hora"}
RECORD_GROUPABLE_FIELDS = (
    frozenset(RECORD_COLUMNS) - {"id", "latitude", "longitude"}
) | {"ano", "mes", "hora"}
RECORD_OUTPUT_FIELDS = frozenset(RECORD_COLUMNS) | {"ano", "mes", "hora"}

ANALYTIC_METRICS = (
    "acidentes", "mortos", "feridos", "feridos_leves", "feridos_graves",
    "pessoas", "ilesos", "ignorados", "veiculos",
)

RECORD_INTEGER_FIELDS = frozenset({
    "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
    "ignorados", "feridos", "veiculos",
})

RECORD_FLOAT_FIELDS = frozenset({"km", "latitude", "longitude"})
