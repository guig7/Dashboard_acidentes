"""Workers AI query planning and grounded response synthesis."""

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
MAX_TOOL_CALLS = 5
MAX_PLAN_COMPLETION_TOKENS = 512
MAX_ANSWER_COMPLETION_TOKENS = 700
MAX_ANSWER_LENGTH = 2000

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
        "description": (
            "Lista as causas registradas mais frequentes no período. Para identificar "
            "a causa com mais acidentes, use limite=1."
        ),
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
            "Consulta distribuições históricas por categorias, inclusive UF/estado. "
            "Use quando perguntarem qual categoria tem mais ou menos acidentes, mortes "
            "ou feridos. Para saber qual estado teve mais acidentes em um ano, use "
            "dimensao='uf', metrica='acidentes' e por_pagina=1."
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
    "com dados de 2017 a 2024. Identifique todas as partes da pergunta e selecione "
    "uma chamada de ferramenta para cada parte, com no máximo cinco chamadas. "
    "Não responda apenas a primeira parte de uma pergunta composta. "
    "Extraia somente filtros explicitamente pedidos; nunca invente um ano ou UF. "
    "Use consultar_serie para séries anuais das métricas disponíveis. "
    "Use consultar_distribuicao para comparar categorias, inclusive condições meteorológicas "
    "e UFs. Se perguntarem qual estado/UF teve mais acidentes, mortes ou feridos em um ano, "
    "use dimensao='uf' e por_pagina=1; por exemplo, 'Qual o estado com mais acidentes em "
    "2020?' corresponde a ano=2020, dimensao='uf', metrica='acidentes', por_pagina=1. "
    "Não recuse essas perguntas por falta de dados: há distribuições por UF preparadas. "
    "Para pergunta composta como 'Qual estado teve mais acidentes em 2023 e qual a maior "
    "causa nesse período?', chame consultar_distribuicao para a UF e listar_causas com "
    "ano=2023 e limite=1. "
    "Contagens históricas não demonstram causalidade nem justificam alertas operacionais. "
    "Use recusar_pergunta para previsões futuras, risco sem denominador de exposição, "
    "ou perguntas sem suporte nos dados. Não misture recusar_pergunta com consultas. "
    "Não calcule nem escreva respostas."
)
_ANSWER_SYSTEM_PROMPT = (
    "Você é um analista de dados que responde em português do Brasil, com tom natural, "
    "claro e respeitoso. Responda a todos os pontos da pergunta em duas a cinco frases, "
    "integrando os resultados das consultas em uma explicação breve e útil. "
    "Use exclusivamente os dados estruturados fornecidos; não invente valores, "
    "comparações, percentuais ou causas. Preserve os "
    "números e recortes retornados. Trate causas como causas registradas na base, sem "
    "afirmar causalidade. Contagens não são medidas de risco sem dados de exposição ao "
    "tráfego e não justificam alertas operacionais. Se algum ponto não estiver respondido "
    "pelos dados, diga isso claramente sem omitir os demais. Não mencione ferramentas ou "
    "detalhes internos. Cite o recorte temporal e encerre com a fonte fornecida."
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
        "parallel_tool_calls": True,
        "chat_template_kwargs": {"enable_thinking": False},
        "max_completion_tokens": MAX_PLAN_COMPLETION_TOKENS,
        "temperature": 0,
        "store": False,
    }


def build_answer_options(
    question: str,
    consultations: list[dict[str, object]],
) -> dict[str, object]:
    context = json.dumps(
        {"pergunta": question, "consultas": consultations, "fonte": SOURCE},
        ensure_ascii=False,
    )
    return {
        "messages": [
            {"role": "system", "content": _ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
        "max_completion_tokens": MAX_ANSWER_COMPLETION_TOKENS,
        "temperature": 0.2,
        "store": False,
    }


def analyze_question(
    question: str,
    summaries: Mapping[str, object],
    infer: Callable[[dict[str, object]], object],
    distribution_loader: DistributionLoader | None = None,
) -> dict[str, object]:
    options = build_inference_options(question)
    tool_selections = _parse_tool_selections(infer(options))

    if len(tool_selections) == 1 and tool_selections[0][0] == "recusar_pergunta":
        _, arguments = tool_selections[0]
        _check_arguments(arguments, {"motivo"})
        reason = arguments.get("motivo")
        if not isinstance(reason, str) or reason not in _REFUSAL_REASONS:
            raise AnalystAIError("Workers AI retornou um motivo de recusa inválido.")
        return _refusal(reason)

    if any(name == "recusar_pergunta" for name, _ in tool_selections):
        raise AnalystAIError("Workers AI misturou recusa e consultas.")

    consultations = []
    for tool_name, arguments in tool_selections:
        if tool_name not in _TOOLS_BY_NAME or tool_name == "recusar_pergunta":
            raise AnalystAIError("Workers AI selecionou uma operação desconhecida.")
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

        consultations.append({
            "operacao": tool_name,
            "filtros": result["filtros"],
            "resultado": result["resultado"],
        })

    answer_response = infer(build_answer_options(question, consultations))
    answer = _parse_answer_text(answer_response)
    if SOURCE.casefold() not in answer.casefold():
        answer = f"{answer.rstrip()} Fonte: {SOURCE}"

    query_descriptions = [
        {"operacao": item["operacao"], "filtros": item["filtros"]}
        for item in consultations
    ]
    results = [item["resultado"] for item in consultations]
    return {
        "status": "respondida",
        "resposta": answer,
        "consulta": query_descriptions[0] if len(consultations) == 1 else query_descriptions,
        "resultado": results[0] if len(consultations) == 1 else results,
        "consultas": consultations,
        "fonte": SOURCE,
    }


def _parse_tool_selections(
    response: object,
) -> list[tuple[str, Mapping[str, object]]]:
    response_value = _as_mapping(response)
    choices = response_value.get("choices")
    if isinstance(choices, list) and choices:
        choice = _as_mapping(choices[0])
        message = _as_mapping(choice.get("message"))
        tool_calls = message.get("tool_calls")
    else:
        tool_calls = response_value.get("tool_calls")

    if not isinstance(tool_calls, list) or not tool_calls:
        return [("recusar_pergunta", {"motivo": "fora_do_escopo"})]
    if len(tool_calls) > MAX_TOOL_CALLS:
        raise AnalystAIError(
            f"Workers AI selecionou mais de {MAX_TOOL_CALLS} consultas."
        )

    selections = []
    for tool_call in tool_calls:
        tool_call_value = _as_mapping(tool_call)
        function = tool_call_value.get("function", tool_call_value)
        function_value = _as_mapping(function)
        name = function_value.get("name")
        raw_arguments = function_value.get("arguments")
        if not isinstance(name, str) or not isinstance(raw_arguments, (str, Mapping)):
            raise AnalystAIError("Workers AI retornou uma chamada de ferramenta inválida.")

        if isinstance(raw_arguments, str):
            try:
                arguments_value = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise AnalystAIError(
                    "Workers AI retornou argumentos que não são JSON válido."
                ) from error
        else:
            arguments_value = raw_arguments

        selections.append((name, _as_mapping(arguments_value)))
    return selections


def _parse_answer_text(response: object) -> str:
    response_value = _as_mapping(response)
    choices = response_value.get("choices")
    if isinstance(choices, list) and choices:
        choice = _as_mapping(choices[0])
        message = _as_mapping(choice.get("message"))
        content = message.get("content")
    else:
        content = response_value.get("response")

    if not isinstance(content, str) or not content.strip():
        content = response_value.get("response")
    if not isinstance(content, str) or not content.strip():
        raise AnalystAIError("Workers AI não retornou uma resposta textual.")
    answer = content.strip()
    if len(answer) > MAX_ANSWER_LENGTH:
        raise AnalystAIError("Workers AI retornou uma resposta acima do limite permitido.")
    return answer


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
