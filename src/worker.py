"""Cloudflare Worker entry point for the PRF dashboard."""

import json

from flask import Flask, Response, abort, jsonify, request
from js import Object
from pyodide.ffi import run_sync, to_js, to_py
from workers import wsgi

from analyst_ai import (
    MODEL_ID,
    AnalystAIError,
    analyze_question,
    is_ai_enabled,
    validate_question,
)
from analyst_queries import QueryDataError, QueryValidationError, execute_query

app = Flask(__name__)
_summary_cache = None

YEARS = {str(year) for year in range(2017, 2025)}
STATES = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}


def filter_key():
    year = request.args.get("ano", "")
    state = request.args.get("uf", "").upper()
    if year and year not in YEARS:
        abort(400, description="Ano inválido. Use um ano entre 2017 e 2024.")
    if state and state not in STATES:
        abort(400, description="UF inválida.")
    parts = []
    if year:
        parts.append(f"year_{year}")
    if state:
        parts.append(f"uf_{state}")
    return "_".join(parts) or "all"


def asset_response(path):
    """Read one prebuilt static asset through the Workers Static Assets binding."""
    assets = request.environ["workers.env"].ASSETS
    return run_sync(assets.fetch(f"https://assets.local/{path}"))


def load_summaries():
    global _summary_cache
    if _summary_cache is None:
        response = asset_response("data/summary.json")
        if response.status >= 400:
            abort(503, description="Dados não encontrados. Gere-os com tools/build_data.py.")
        _summary_cache = json.loads(run_sync(response.text()))
    return _summary_cache


def summary_value(name):
    key = filter_key()
    entry = load_summaries().get(key)
    if entry is None:
        abort(503, description="Dados do dashboard ausentes para este filtro.")
    return jsonify(entry[name])


@app.get("/api/stats_gerais")
def stats_gerais():
    return summary_value("stats_gerais")


@app.get("/api/acidentes_por_ano")
def acidentes_por_ano():
    return summary_value("acidentes_por_ano")


@app.get("/api/mortos_por_ano")
def mortos_por_ano():
    return summary_value("mortos_por_ano")


@app.get("/api/causas")
def top_causas():
    return summary_value("causas")


@app.get("/api/estados")
def acidentes_ufs():
    return summary_value("estados")


@app.get("/api/taxa_severidade")
def taxa_severidade():
    return summary_value("taxa_severidade")


@app.get("/api/heatmap_horarios")
def heatmap_horarios():
    return summary_value("heatmap_horarios")


@app.get("/api/ranking_estados")
def ranking_estados():
    return summary_value("ranking_estados")


@app.post("/api/analista/consulta")
def consulta_analista():
    if not request.is_json:
        abort(400, description="Envie o corpo da consulta com Content-Type application/json.")
    try:
        result = execute_query(load_summaries(), request.get_json())
    except QueryValidationError as error:
        abort(400, description=str(error))
    except QueryDataError as error:
        abort(503, description=str(error))
    return jsonify(result)


@app.get("/api/analista/status")
def status_analista():
    env = request.environ["workers.env"]
    return jsonify({"habilitado": is_ai_enabled(env)})


@app.post("/api/analista/perguntar")
def perguntar_analista():
    if not request.is_json:
        abort(400, description="Envie a pergunta com Content-Type application/json.")
    payload = request.get_json()
    if not isinstance(payload, dict) or set(payload) != {"pergunta"}:
        abort(400, description="O corpo deve conter somente o campo 'pergunta'.")
    try:
        question = validate_question(payload["pergunta"])
    except QueryValidationError as error:
        abort(400, description=str(error))

    env = request.environ["workers.env"]
    if getattr(env, "ANALYST_AI_ENABLED", "false") != "true":
        abort(503, description="O analista com IA está desativado.")
    ai_binding = getattr(env, "AI", None)
    if ai_binding is None:
        abort(503, description="Binding Workers AI não configurado.")
    rate_limiter = getattr(env, "ANALYST_RATE_LIMITER", None)
    if rate_limiter is None:
        abort(503, description="Proteção contra excesso de chamadas não configurada.")

    rate_limit_key = request.headers.get("CF-Connecting-IP") or "anonymous"
    rate_limit_options = to_js(
        {"key": rate_limit_key},
        dict_converter=Object.fromEntries,
    )
    rate_limit_result = run_sync(rate_limiter.limit(rate_limit_options))
    rate_limit_success = getattr(rate_limit_result, "success", None)
    if rate_limit_success is None:
        abort(503, description="Não foi possível verificar o limite de chamadas.")
    if not bool(rate_limit_success):
        abort(429, description="Limite de consultas atingido. Tente novamente em um minuto.")

    def infer(options):
        js_options = to_js(options, dict_converter=Object.fromEntries)
        response = run_sync(ai_binding.run(MODEL_ID, js_options))
        return to_py(response)

    try:
        result = analyze_question(question, load_summaries(), infer)
    except AnalystAIError as error:
        abort(502, description=str(error))
    except QueryDataError as error:
        abort(503, description=str(error))
    return jsonify(result)


@app.get("/api/mapa")
def mapa_acidentes():
    key = filter_key()
    response = asset_response(f"data/maps/{key}.json")
    if response.status >= 400:
        abort(503, description="Dados do mapa ausentes. Gere-os com tools/build_data.py.")
    return Response(
        run_sync(response.bytes()),
        status=response.status,
        content_type="application/json; charset=utf-8",
    )


@app.get("/api/tabela_detalhada")
def tabela_detalhada():
    key = filter_key()
    response = asset_response(f"data/tables/{key}.json")
    if response.status >= 400:
        abort(503, description="Dados da tabela ausentes. Gere-os com tools/build_data.py.")
    return Response(
        run_sync(response.bytes()),
        status=response.status,
        content_type="application/json; charset=utf-8",
    )


@app.errorhandler(400)
@app.errorhandler(429)
@app.errorhandler(502)
@app.errorhandler(404)
@app.errorhandler(503)
def json_error(error):
    return jsonify({"erro": getattr(error, "description", "Recurso indisponível.")}), error.code


Default = wsgi.entrypoint(app)
