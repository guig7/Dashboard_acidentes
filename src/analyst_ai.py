"""Workers AI intent extraction for the deterministic analyst queries."""

import json
from collections.abc import Callable, Mapping
from typing import cast

from analyst_queries import (
    ANALYTIC_DIMENSIONS,
    DISTRIBUTION_METRICS,
    METRICS,
    DistributionLoader,
    QueryDataError,
    QueryValidationError,
    SOURCE,
    STATES,
    execute_query,
)

MODEL_ID = "@cf/zai-org/glm-4.7-flash"
MAX_QUESTION_LENGTH = 500
MAX_COMPLETION_TOKENS = 160

_STATE_ENUM = sorted(STATES)
_METRIC_ENUM = list(METRICS)
_REFUSAL_REASONS = {
    "fora_do_escopo": "Não consigo responder a essa pergunta com as consultas disponíveis no painel.",
    "previsao_futura": "O painel contém registros históricos e não permite prever acidentes futuros.",
    "sem_denominador_de_exposicao": "O painel não contém dados de exposição ao tráfego para calcular risco por veículo ou distância.",
    "dados_insuficientes": "Não encontrei dados suficientes no painel para responder a essa pergunta.",
}

_TOOL_DEFINITIONS = [
    {
        "name": "consultar_resumo",
        "description": "Consulta totais de acidentes, mortes e feridos no período selecionado.",
        "parameters": {
            "type": "object",
            "properties": {
                "ano": {"type": "integer", "minimum": 2017, "maximum": 2024},
                "uf": {"type": "string", "enum": _STATE_ENUM},
                "metrica": {"type": "string", "enum": _METRIC_ENUM},
            },
        },
    },
    {
        "name": "comparar_estados",
        "description": "Compara uma métrica entre duas ou mais UFs, opcionalmente em um ano.",
        "parameters": {
            "type": "object",
            "properties": {
                "ano": {"type": "integer", "minimum": 2017, "maximum": 2024},
                "ufs": {
                    "type": "array",
                    "items": {"type": "string", "enum": _STATE_ENUM},
                    "minItems": 2,
                    "maxItems": 10,
                },
                "metrica": {"type": "string", "enum": _METRIC_ENUM},
            },
            "required": ["ufs", "metrica"],
        },
    },
    {
        "name": "listar_causas",
        "description": "Lista as causas mais frequentes no período selecionado.",
        "parameters": {
            "type": "object",
            "properties": {
                "ano": {"type": "integer", "minimum": 2017, "maximum": 2024},
                "uf": {"type": "string", "enum": _STATE_ENUM},
                "limite": {"type": "integer", "minimum": 1, "maximum": 10},
            },
        },
    },
    {
        "name": "consultar_serie",
        "description": "Consulta uma série anual de acidentes ou mortes.",
        "parameters": {
            "type": "object",
            "properties": {
                "uf": {"type": "string", "enum": _STATE_ENUM},
                "metrica": {"type": "string", "enum": sorted(METRICS)},
                "ano_inicio": {"type": "integer", "minimum": 2017, "maximum": 2024},
                "ano_fim": {"type": "integer", "minimum": 2017, "maximum": 2024},
            },
            "required": ["metrica"],
        },
    },
    {
        "name": "consultar_distribuicao",
        "description": (
            "Consulta a distribuição histórica por condição meteorológica, causa, tipo, "
            "município, BR, hora e outras categorias disponíveis no painel."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ano": {"type": "integer", "minimum": 2017, "maximum": 2024},
                "uf": {"type": "string", "enum": _STATE_ENUM},
                "dimensao": {
                    "type": "string",
                    "enum": sorted(ANALYTIC_DIMENSIONS),
                },
                "metrica": {
                    "type": "string",
                    "enum": sorted(DISTRIBUTION_METRICS),
                },
                "pagina": {"type": "integer", "minimum": 1},
                "por_pagina": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["dimensao", "metrica"],
        },
    },
    {
        "name": "recusar_pergunta",
        "description": "Use quando a pergunta não puder ser respondida com os dados do painel.",
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "enum": sorted(_REFUSAL_REASONS),
                },
            },
            "required": ["motivo"],
        },
    },
]

TOOLS = [
    {"type": "function", "function": definition}
    for definition in _TOOL_DEFINITIONS
]
_TOOLS_BY_NAME = {
    tool["function"]["name"]: tool["function"]
    for tool in TOOLS
}
_SYSTEM_PROMPT = (
    "Você classifica perguntas sobre um painel de acidentes da PRF no Brasil, "
    "com dados de 2017 a 2024. Selecione exatamente uma ferramenta. "
    "Extraia somente filtros explicitamente pedidos; nunca invente um ano ou UF. "
    "Use consultar_serie para séries anuais das métricas disponíveis. "
    "Use consultar_distribuicao para comparar categorias, inclusive condições meteorológicas. "
    "Contagens históricas não demonstram causalidade nem justificam alertas operacionais. "
    "Use recusar_pergunta para previsões futuras, risco sem denominador de exposição, "
    "ou perguntas sem suporte nos dados. Não calcule nem escreva respostas."
)


class AnalystAIError(ValueError):
    """Raised when Workers AI returns an unusable tool selection."""


def is_ai_enabled(env: object) -> bool:
    return (
        getattr(env, "ANALYST_AI_ENABLED", "false") == "true"
        and getattr(env, "AI", None) is not None
        and getattr(env, "ANALYST_RATE_LIMITER", None) is not None
    )


def validate_question(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise QueryValidationError("Informe uma pergunta em 'pergunta'.")
    question = value.strip()
    if len(question) > MAX_QUESTION_LENGTH:
        raise QueryValidationError(
            f"A pergunta deve ter no máximo {MAX_QUESTION_LENGTH} caracteres."
        )
    return question


def build_inference_options(question: str) -> dict[str, object]:
    return {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        "tools": TOOLS,
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "chat_template_kwargs": {"enable_thinking": False},
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "temperature": 0,
        "store": False,
    }


def analyze_question(
    question: str,
    summaries: Mapping[str, object],
    infer: Callable[[dict[str, object]], object],
    distribution_loader: DistributionLoader | None = None,
) -> dict[str, object]:
    options = build_inference_options(question)
    tool_name, arguments = _parse_tool_selection(infer(options))

    if tool_name == "recusar_pergunta":
        _check_arguments(arguments, {"motivo"})
        reason = arguments.get("motivo")
        if not isinstance(reason, str) or reason not in _REFUSAL_REASONS:
            raise AnalystAIError("Workers AI retornou um motivo de recusa inválido.")
        return _refusal(reason)

    if tool_name not in _TOOLS_BY_NAME:
        raise AnalystAIError("Workers AI selecionou uma operação desconhecida.")
    if tool_name == "consultar_distribuicao" and "por_pagina" in arguments:
        page_size = arguments["por_pagina"]
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 10
        ):
            raise AnalystAIError("Workers AI retornou um tamanho de página inválido.")

    try:
        result = execute_query(
            summaries,
            {"operacao": tool_name, **arguments},
            distribution_loader=distribution_loader,
        )
    except QueryValidationError:
        return _refusal("dados_insuficientes")
    except QueryDataError:
        raise

    return {
        "status": "respondida",
        "resposta": _format_answer(tool_name, result["filtros"], result["resultado"]),
        "consulta": {
            "operacao": tool_name,
            "filtros": result["filtros"],
        },
        "resultado": result["resultado"],
        "fonte": SOURCE,
    }


def _parse_tool_selection(response: object) -> tuple[str, Mapping[str, object]]:
    response_value = _as_mapping(response)
    choices = response_value.get("choices")
    if isinstance(choices, list) and choices:
        choice = _as_mapping(choices[0])
        message = _as_mapping(choice.get("message"))
        tool_calls = message.get("tool_calls")
    else:
        tool_calls = response_value.get("tool_calls")

    if not isinstance(tool_calls, list) or not tool_calls:
        return "recusar_pergunta", {"motivo": "fora_do_escopo"}
    if len(tool_calls) != 1:
        raise AnalystAIError("Workers AI deve selecionar exatamente uma operação.")

    tool_call = _as_mapping(tool_calls[0])
    function = tool_call.get("function", tool_call)
    function_value = _as_mapping(function)
    name = function_value.get("name")
    raw_arguments = function_value.get("arguments")
    if not isinstance(name, str) or not isinstance(raw_arguments, (str, Mapping)):
        raise AnalystAIError("Workers AI retornou uma chamada de ferramenta inválida.")

    if isinstance(raw_arguments, str):
        try:
            arguments_value = json.loads(raw_arguments)
        except json.JSONDecodeError as error:
            raise AnalystAIError("Workers AI retornou argumentos que não são JSON válido.") from error
    else:
        arguments_value = raw_arguments

    arguments = _as_mapping(arguments_value)
    return name, arguments


def _format_answer(
    operation: str,
    filters: object,
    result: object,
) -> str:
    filter_values = _as_mapping(filters)
    period = _period_text(filter_values.get("ano"))
    state = filter_values.get("uf")
    if isinstance(state, str):
        period += f" em {state}"

    if operation == "consultar_resumo":
        metrics = _as_mapping(result)
        labels = {
            "acidentes": "acidentes",
            "mortes": "mortes",
            "feridos": "feridos",
            "feridos_leves": "feridos leves",
            "feridos_graves": "feridos graves",
            "pessoas": "pessoas envolvidas",
            "ilesos": "ilesos",
            "ignorados": "registros ignorados",
            "veiculos": "veículos envolvidos",
        }
        values = [
            f"{_format_number(value)} {labels[key]}"
            for key, value in metrics.items()
            if key in labels and isinstance(value, int)
        ]
        return f"No recorte {period}, foram registrados " + " e ".join(values) + "."

    if operation == "comparar_estados" and isinstance(result, list):
        comparison_year = filter_values.get("ano")
        comparison_period = _period_text(comparison_year)
        metric = filter_values.get("metrica")
        metric_label = {
            "acidentes": "acidentes",
            "mortes": "mortes",
            "feridos": "feridos",
            "feridos_leves": "feridos leves",
            "feridos_graves": "feridos graves",
            "pessoas": "pessoas envolvidas",
            "ilesos": "ilesos",
            "ignorados": "registros ignorados",
            "veiculos": "veículos envolvidos",
        }.get(metric, "registros")
        values = [
            f"{row['uf']} registrou {_format_number(row['valor'])} {metric_label}"
            for item in result
            if isinstance(item, Mapping)
            for row in [cast(Mapping[str, object], item)]
            if isinstance(row.get("uf"), str) and isinstance(row.get("valor"), int)
        ]
        return f"Em {comparison_period}, " + "; ".join(values) + "."

    if operation == "listar_causas" and isinstance(result, list):
        causes = [
            f"{row['causa']} ({_format_number(row['acidentes'])} acidentes)"
            for item in result
            if isinstance(item, Mapping)
            for row in [cast(Mapping[str, object], item)]
            if isinstance(row.get("causa"), str) and isinstance(row.get("acidentes"), int)
        ]
        return f"As causas mais frequentes no recorte {period} foram: " + "; ".join(causes) + "."

    if operation == "consultar_serie" and isinstance(result, list):
        metric = filter_values.get("metrica")
        metric_label = {
            "acidentes": "acidentes",
            "mortes": "mortes",
            "feridos": "feridos",
            "feridos_leves": "feridos leves",
            "feridos_graves": "feridos graves",
            "pessoas": "pessoas envolvidas",
            "ilesos": "ilesos",
            "ignorados": "registros ignorados",
            "veiculos": "veículos envolvidos",
        }.get(metric, "registros")
        points = [
            f"{point['ano']}: {_format_number(point['valor'])}"
            for item in result
            if isinstance(item, Mapping)
            for point in [cast(Mapping[str, object], item)]
            if isinstance(point.get("ano"), int) and isinstance(point.get("valor"), int)
        ]
        return f"Série anual de {metric_label} no recorte {period}: " + "; ".join(points) + "."

    if operation == "consultar_distribuicao" and isinstance(result, list):
        metric = filter_values.get("metrica")
        dimension = filter_values.get("dimensao")
        metric_label = {
            "acidentes": "acidentes",
            "mortes": "mortes",
            "feridos": "feridos",
            "feridos_leves": "feridos leves",
            "feridos_graves": "feridos graves",
            "pessoas": "pessoas",
            "ilesos": "ilesos",
            "ignorados": "registros ignorados",
            "veiculos": "veículos envolvidos",
        }.get(metric, "registros")
        dimension_label = ANALYTIC_DIMENSIONS.get(dimension, "categoria")
        values = [
            f"{row['valor']}: {_format_number(row[metric])} {metric_label}"
            for item in result
            if isinstance(item, Mapping)
            for row in [cast(Mapping[str, object], item)]
            if isinstance(row.get("valor"), str) and isinstance(row.get(metric), int)
        ]
        answer = (
            f"No recorte {period}, as categorias de {dimension_label} com mais "
            f"{metric_label} foram: " + "; ".join(values) + "."
        )
        if dimension == "condicao_metereologica":
            answer += (
                " São contagens históricas; não demonstram causalidade nem constituem "
                "alerta operacional."
            )
        return answer

    raise AnalystAIError("Não foi possível compor a resposta da consulta.")


def _period_text(year: object) -> str:
    if isinstance(year, int):
        return f"de {year}"
    return "de 2017 a 2024"


def _format_number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _refusal(reason: str) -> dict[str, object]:
    return {
        "status": "recusada",
        "resposta": _REFUSAL_REASONS[reason],
        "motivo": reason,
        "consulta": None,
        "resultado": None,
        "fonte": SOURCE,
    }


def _check_arguments(arguments: Mapping[str, object], allowed: set[str]) -> None:
    if set(arguments) - allowed:
        raise AnalystAIError("Workers AI retornou argumentos não suportados.")


def _as_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise AnalystAIError("Workers AI retornou uma resposta inválida.")
    return cast(Mapping[str, object], value)
