from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import ValidationError

from .config import LLMSettings, get_llm_settings, load_local_environment
from .llm_client import LLMHttpClient
from .prevent import estratificar_risco_cardio
from .schemas import (
    ClassificarPAArgs,
    ContraindicacaoArgs,
    MedicamentoVerificado,
    PacienteHAS,
    RiskToolArgs,
    SaidaAgente,
    VerificarMedicamentoArgs,
)
from .tools import (
    MEDICAMENTOS_SUS,
    checar_contraindicacao,
    classificar_pa,
    verificar_confirmacao_pa,
    verificar_medicamento_sus,
    verificar_red_flags_infarto,
)

MAX_TURNOS = 6
MAX_TOOL_CALLS = 16
_SUFIXOS_FARMACOS = ("pril", "sartan", "sartana", "olol", "dipino", "dipina", "dipine", "tiazida", "thiazide")


@dataclass
class ToolTrace:
    nome: str
    argumentos: dict[str, Any]
    resultado: dict[str, Any]
    origem: Literal["preflight", "llm"]
    executada: bool = True


@dataclass
class AgentRun:
    saida: SaidaAgente
    ferramentas: list[ToolTrace]
    fluxo_abortado: bool

    def model_dump(self) -> dict[str, Any]:
        return {
            "saida": self.saida.model_dump(mode="json"),
            "ferramentas": [asdict(item) for item in self.ferramentas],
            "fluxo_abortado": self.fluxo_abortado,
        }


def _norm(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain).strip()


def _menciona_farmaco(text: str) -> bool:
    normalized = _norm(text)
    aliases = {alias for group in MEDICAMENTOS_SUS.values() for alias in group}
    if any(_norm(alias) in normalized for alias in aliases):
        return True
    words = re.findall(r"[a-z]+", normalized)
    return any(word.endswith(suffix) for word in words for suffix in _SUFIXOS_FARMACOS)


def _contains_sensitive_identifier(case: PacienteHAS) -> bool:
    text_values = list(case.comorbidades) + list(case.sintomas_atuais or []) + list(case.dados_faltantes)
    text_values.extend(med.nome for med in case.medicamentos_em_uso or [])
    text_values.extend(med.dose or "" for med in case.medicamentos_em_uso or [])
    text_values.extend(med.frequencia or "" for med in case.medicamentos_em_uso or [])
    combined = " ".join(text_values)
    patterns = (
        r"\b\d{3}[.\s-]?\d{3}[.\s-]?\d{3}[.\s-]?\d{2}\b",
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        r"\b(?:nome(?:\s+completo)?|cpf|rg|prontu[aá]rio|matr[ií]cula|endere[cç]o|telefone|e-mail)\s*[:=]",
    )
    return any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns)


def _redact_runtime_labels(text: str, settings: LLMSettings) -> str:
    parsed = urlparse(settings.base_url)
    generic_tokens = {
        "api", "www", "chat", "com", "net", "org", "io", "ai", "gov", "br", "app",
        "cloud", "local", "localhost", "model", "modelo", "llm", "chat", "instruct",
        "reasoner", "turbo", "flash", "mini", "large", "small", "fast", "latest",
        "preview", "standard", "pro", "v1", "v2", "v3", "v4",
    }
    labels: set[str] = set()
    if settings.base_url:
        labels.add(settings.base_url.strip())
    if settings.model_name:
        labels.add(settings.model_name.strip())
    for label in (parsed.hostname or "").split("."):
        if len(label) >= 4 and label.casefold() not in generic_tokens:
            labels.add(label)
            labels.update(
                part for part in re.split(r"[-_]", label)
                if len(part) >= 4 and part.casefold() not in generic_tokens
            )
    for label in sorted((item for item in labels if item), key=len, reverse=True):
        text = re.sub(rf"(?<![\w]){re.escape(label)}(?![\w])", "Pulso+", text, flags=re.IGNORECASE)
    return text


def _tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


OBJECT_NO_EXTRA = {"type": "object", "additionalProperties": False}
TOOL_DEFINITIONS = [
    _tool(
        "classificar_pa",
        "Classifica a última PA completa. O servidor compara os argumentos com a aferição documentada e injeta sintomas do caso.",
        {
            **OBJECT_NO_EXTRA,
            "properties": {
                "pas": {"type": "integer", "description": "PAS explícita em mmHg"},
                "pad": {"type": "integer", "description": "PAD explícita em mmHg"},
                "sintomas": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["pas", "pad"],
        },
    ),
    _tool(
        "estratificar_risco_cardio",
        "Calcula PREVENT-CVD em 10 anos; se faltar variável obrigatória, retorna risco indeterminado e lista os campos ausentes. Não estime nem impute.",
        {
            **OBJECT_NO_EXTRA,
            "properties": {
                "idade": {"type": ["integer", "null"]},
                "sexo": {"type": ["string", "null"], "enum": ["M", "F", None]},
                "pas": {"type": ["number", "null"]},
                "colesterol_total": {"type": ["number", "null"]},
                "hdl": {"type": ["number", "null"]},
                "diabetes": {"type": ["boolean", "null"]},
                "tabagismo": {"type": ["boolean", "null"]},
                "imc": {"type": ["number", "null"]},
                "drfg_estimada": {"type": ["number", "null"]},
                "em_uso_anti_hipertensivo": {"type": ["boolean", "null"]},
                "em_uso_estatina": {"type": ["boolean", "null"]},
                "doenca_cardiovascular_previa": {"type": ["boolean", "null"]},
            },
            "required": [],
        },
    ),
    _tool(
        "verificar_medicamento_sus",
        "Verifica se o nome genérico está na allowlist SUS/RENAME configurada.",
        {**OBJECT_NO_EXTRA, "properties": {"medicamento": {"type": "string"}}, "required": ["medicamento"]},
    ),
    _tool(
        "checar_contraindicacao",
        "Checa contraindicações mínimas usando condições e exames do caso fornecidos pelo servidor.",
        {
            **OBJECT_NO_EXTRA,
            "properties": {
                "medicamento": {"type": "string"},
                "condicoes": {"type": "array", "items": {"type": "string"}},
                "exames": {"type": "object"},
            },
            "required": ["medicamento"],
        },
    ),
]

_TOOL_MODELS = {
    "classificar_pa": ClassificarPAArgs,
    "estratificar_risco_cardio": RiskToolArgs,
    "verificar_medicamento_sus": VerificarMedicamentoArgs,
    "checar_contraindicacao": ContraindicacaoArgs,
}


class ClinicalAgent:
    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        model_name: str | None = None,
        max_turnos: int = MAX_TURNOS,
        system_prompt_path: Path | None = None,
    ) -> None:
        load_local_environment()
        environment = get_llm_settings()
        self.settings = LLMSettings(
            api_key=api_key if api_key is not None else environment.api_key,
            base_url=base_url if base_url is not None else environment.base_url,
            model_name=model_name if model_name is not None else environment.model_name,
        )
        self.max_turnos = max_turnos
        self.client = client
        self.system_prompt_path = system_prompt_path or Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.md"

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.settings.ready:
            raise RuntimeError("Configuração do motor incompleta.")
        self.client = LLMHttpClient(self.settings)
        return self.client

    def _system_prompt(self) -> str:
        return self.system_prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _positive_condition(conditions: list[str], patterns: tuple[str, ...]) -> bool | None:
        normalized = [_norm(item) for item in conditions]
        return True if any(any(pattern in item for pattern in patterns) for item in normalized) else None

    @staticmethod
    def _medication_flags(case: PacienteHAS) -> tuple[bool | None, bool | None]:
        if case.em_uso_anti_hipertensivo is not None:
            anti_htn = case.em_uso_anti_hipertensivo
        elif case.medicamentos_em_uso is not None:
            recognized = [verificar_medicamento_sus(med.nome)["disponivel_sus"] for med in case.medicamentos_em_uso]
            anti_htn = True if any(recognized) else (False if not case.medicamentos_em_uso else None)
        else:
            anti_htn = None

        if case.em_uso_estatina is not None:
            statin = case.em_uso_estatina
        elif case.medicamentos_em_uso is not None:
            statin_names = {"atorvastatina", "sinvastatina", "rosuvastatina", "pravastatina", "fluvastatina", "pitavastatina"}
            names = [re.sub(r"\s+\d+(?:[.,]\d+)?\s*(?:mg|mcg|g)\b.*$", "", _norm(med.nome)) for med in case.medicamentos_em_uso]
            statin = True if any(name in statin_names for name in names) else (False if not case.medicamentos_em_uso else None)
        else:
            statin = None
        return anti_htn, statin

    def _canonical_risk_args(self, case: PacienteHAS) -> dict[str, Any]:
        latest = case.consulta_mais_recente()
        anti_htn, statin = self._medication_flags(case)
        diabetes = case.diabetes
        if diabetes is None:
            diabetes = self._positive_condition(case.comorbidades, ("diabetes",))
        prior_cvd = case.doenca_cardiovascular_previa
        if prior_cvd is None:
            prior_cvd = self._positive_condition(
                case.comorbidades,
                ("infarto", "avc", "acidente vascular cerebral", "doenca coronariana", "insuficiencia cardiaca"),
            )
        return {
            "idade": case.idade,
            "sexo": case.sexo,
            "pas": latest.pas if latest else None,
            "colesterol_total": case.exames_recentes.colesterol_total,
            "hdl": case.exames_recentes.hdl,
            "diabetes": diabetes,
            "tabagismo": case.tabagismo_atual,
            "imc": case.exames_recentes.imc,
            "drfg_estimada": case.exames_recentes.drfg_estimada,
            "em_uso_anti_hipertensivo": anti_htn,
            "em_uso_estatina": statin,
            "doenca_cardiovascular_previa": prior_cvd,
        }

    @staticmethod
    def _case_conditions(case: PacienteHAS) -> list[str]:
        conditions = list(case.comorbidades)
        if case.gestante:
            conditions.append("gestação")
        if case.suspeita_hipertensao_secundaria:
            conditions.append("suspeita de hipertensão secundária")
        return conditions

    @staticmethod
    def _case_exams(case: PacienteHAS) -> dict[str, Any]:
        return case.exames_recentes.model_dump(exclude_none=True)

    def _audit_meds(self, case: PacienteHAS, trace: list[ToolTrace]) -> tuple[list[MedicamentoVerificado], bool]:
        audits: list[MedicamentoVerificado] = []
        force_review = False
        for medication in case.medicamentos_em_uso or []:
            availability = verificar_medicamento_sus(medication.nome)
            trace.append(ToolTrace("verificar_medicamento_sus", {"medicamento": medication.nome}, availability, "preflight"))
            contraindication = checar_contraindicacao(
                medication.nome,
                self._case_conditions(case),
                self._case_exams(case),
            )
            trace.append(ToolTrace(
                "checar_contraindicacao",
                {"medicamento": medication.nome, "condicoes": self._case_conditions(case), "exames": self._case_exams(case)},
                contraindication,
                "preflight",
            ))
            audits.append(MedicamentoVerificado(
                nome=medication.nome,
                disponivel_sus=availability["disponivel_sus"],
                contraindicacao=contraindication["contraindicado"],
            ))
            if not availability["disponivel_sus"] or contraindication["contraindicado"]:
                force_review = True
        return audits, force_review

    @staticmethod
    def _merge_missing(*collections: list[str]) -> list[str]:
        merged: list[str] = []
        for collection in collections:
            for item in collection:
                if item not in merged:
                    merged.append(item)
        return merged

    def _fallback(
        self,
        case: PacienteHAS,
        *,
        reason: str,
        risk_result: dict[str, Any] | None = None,
        missing: list[str] | None = None,
        audits: list[MedicamentoVerificado] | None = None,
        emergency: bool = False,
    ) -> AgentRun:
        risk_result = risk_result or {"risco": "indeterminado", "faltam_dados": []}
        if emergency:
            output = SaidaAgente(
                caso_id=case.caso_id,
                situacao_atual="Alerta vermelho de segurança; fluxo de hipertensão abortado.",
                risco_cardiovascular="indeterminado",
                conduta_sugerida="encaminhar_especialista",
                detalhe_conduta=reason,
                justificativa="Regra determinística de safety net: avaliação urgente antes de qualquer conduta de HAS. O alerta não confirma diagnóstico de infarto.",
                medicamentos_verificados=audits or [],
                nivel_confianca="alto",
                necessita_revisao_humana=True,
                dados_faltantes=missing or ["avaliação clínica urgente presencial"],
            )
        else:
            output = SaidaAgente(
                caso_id=case.caso_id,
                situacao_atual="Caso incompleto ou bloqueado para decisão automática.",
                risco_cardiovascular=risk_result.get("risco", "indeterminado"),
                conduta_sugerida="revisao_humana_necessaria",
                detalhe_conduta=reason,
                justificativa="O backend não recebeu todos os dados necessários ou detectou um bloqueio de segurança; não foi feita inferência clínica por aproximação.",
                medicamentos_verificados=audits or [],
                nivel_confianca="baixo",
                necessita_revisao_humana=True,
                dados_faltantes=self._merge_missing(missing or [], risk_result.get("faltam_dados", [])),
            )
        return AgentRun(saida=output, ferramentas=[], fluxo_abortado=True)

    def analyze(self, raw_case: dict[str, Any] | PacienteHAS) -> AgentRun:
        case = raw_case if isinstance(raw_case, PacienteHAS) else PacienteHAS.model_validate(raw_case)
        trace: list[ToolTrace] = []
        exams = case.exames_recentes

        # Safety net cardiovascular: roda antes de qualquer etapa de hipertensão/LLM.
        safety = verificar_red_flags_infarto(exams.troponina, exams.ckmb, exams.ckmb_limite_superior)
        trace.append(ToolTrace(
            "verificar_red_flags_infarto",
            {"troponina": exams.troponina, "ckmb": exams.ckmb, "ckmb_limite_superior": exams.ckmb_limite_superior},
            safety,
            "preflight",
        ))
        if safety["bloquear_fluxo_hipertensao"]:
            missing = ["avaliação clínica urgente presencial"] if safety["alerta_vermelho"] else ["limite_de_referência_e_unidade_do_CK-MB"]
            run = self._fallback(
                case,
                reason=safety["motivo"],
                missing=missing,
                emergency=safety["alerta_vermelho"],
            )
            run.ferramentas = trace
            return run

        latest = case.consulta_mais_recente()
        symptoms = case.sintomas_atuais or []
        pa_args = {"pas": latest.pas if latest else None, "pad": latest.pad if latest else None, "sintomas": symptoms}
        try:
            pa_result = classificar_pa(pa_args["pas"], pa_args["pad"], symptoms)
        except ValueError as exc:
            pa_result = {
                "classificacao": "indeterminada",
                "status_dados": "invalido",
                "faltam_dados": [],
                "dados_invalidos": [str(exc)],
                "alerta": None,
            }
        trace.append(ToolTrace("classificar_pa", pa_args, pa_result, "preflight"))

        confirmation = verificar_confirmacao_pa([
            {"data": item.data.isoformat() if item.data else None, "pas": item.pas, "pad": item.pad}
            for item in case.consultas
        ])
        trace.append(ToolTrace("verificar_confirmacao_pa", {"consultas": len(case.consultas)}, confirmation, "preflight"))

        risk_args = self._canonical_risk_args(case)
        if pa_result.get("status_dados") == "invalido":
            risk_args["pas"] = None
        risk_result = estratificar_risco_cardio(**risk_args)
        trace.append(ToolTrace("estratificar_risco_cardio", risk_args, risk_result, "preflight"))

        medication_audits, medication_review = self._audit_meds(case, trace)
        if pa_result.get("status_dados") == "invalido":
            run = self._fallback(
                case,
                reason="Aferição de PA fora dos limites operacionais; verificar e repetir antes de qualquer classificação.",
                risk_result=risk_result,
                missing=["PAS/PAD válidas e conferidas"],
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        missing_pa = pa_result.get("faltam_dados", [])
        if missing_pa:
            run = self._fallback(
                case,
                reason="Aferir e registrar PAS e PAD explicitamente antes de classificar ou sugerir conduta para HAS.",
                risk_result=risk_result,
                missing=self._merge_missing(missing_pa, confirmation["faltam_dados"]),
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        if pa_result.get("alerta") == "emergencia_hipertensiva":
            run = self._fallback(
                case,
                reason="PA em faixa grave associada a sintoma compatível com lesão aguda de órgão-alvo; encaminhar para avaliação urgente.",
                risk_result=risk_result,
                missing=["avaliação clínica urgente presencial"],
                audits=medication_audits,
                emergency=True,
            )
            run.ferramentas = trace
            return run

        if pa_result.get("classificacao") == "HAS estágio 3" and case.sintomas_atuais is None:
            run = self._fallback(
                case,
                reason="PA em faixa grave e sintomas de lesão de órgão-alvo não informados; avaliar sintomas e obter revisão clínica antes de seguir.",
                risk_result=risk_result,
                missing=["sintomas_atuais", "avaliação clínica"],
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        out_of_scope: list[str] = []
        if case.idade is not None and case.idade < 18:
            out_of_scope.append("idade_menor_de_18_anos")
        if case.gestante:
            out_of_scope.append("gestação")
        if case.suspeita_hipertensao_secundaria:
            out_of_scope.append("suspeita_de_hipertensão_secundária")
        if out_of_scope:
            run = self._fallback(
                case,
                reason="Caso fora do escopo automatizado; revisão humana sem recomendação farmacológica.",
                risk_result=risk_result,
                missing=self._merge_missing(out_of_scope, confirmation["faltam_dados"]),
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        if medication_review:
            run = self._fallback(
                case,
                reason="Medicamento não confirmado na lista de verificação ou possível contraindicação; não foi enviado ao motor para sugestão.",
                risk_result=risk_result,
                missing=["revisão profissional do esquema terapêutico e das contraindicações"],
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        if _contains_sensitive_identifier(case):
            run = self._fallback(
                case,
                reason="Remova identificadores pessoais dos campos clínicos livres e valide novamente; nenhum dado foi enviado ao motor.",
                risk_result=risk_result,
                missing=["campos clínicos desidentificados"],
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        if not self.settings.ready and self.client is None:
            run = self._fallback(
                case,
                reason="Análise automática não executada: configure o motor antes de solicitar uma sugestão.",
                risk_result=risk_result,
                missing=self._merge_missing(["configuração do motor de análise"], confirmation["faltam_dados"]),
                audits=medication_audits,
            )
            run.ferramentas = trace
            return run

        case_payload = case.model_dump(mode="json")
        # Reduz dados transmitidos: sem ID do caso ou observações livres com possível PHI.
        case_payload["caso_id"] = "CASO_ANONIMIZADO"
        case_payload.pop("observacoes", None)
        precomputed = {
            "caso": case_payload,
            "resultados_deterministicos": [{"ferramenta": item.nome, "resultado": item.resultado} for item in trace],
            "medicamentos_verificados": [item.model_dump() for item in medication_audits],
            "observacao": "Use somente valores observados no caso. Não complete dados ausentes.",
        }
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": json.dumps(precomputed, ensure_ascii=False, allow_nan=False)},
        ]
        tool_call_count = 0
        force_review = medication_review or not confirmation["diagnostico_confirmado"]

        for _turn in range(self.max_turnos):
            try:
                response = self._client().create(
                    messages=messages,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=1800,
                )
            except Exception:
                run = self._fallback(
                    case,
                    reason="Falha ao comunicar com o motor de análise; nenhuma saída automática foi aceita.",
                    risk_result=risk_result,
                    missing=self._merge_missing(["análise automática não concluída"], confirmation["faltam_dados"]),
                    audits=medication_audits,
                )
                run.ferramentas = trace
                return run

            if not isinstance(response, dict) or not isinstance(response.get("choices"), list) or not response["choices"]:
                break
            choice = response["choices"][0]
            message = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(message, dict):
                break
            finish_reason = choice.get("finish_reason")
            tool_calls = message.get("tool_calls") or []

            # Único gatilho permitido para executar funções é finish_reason=tool_calls.
            if finish_reason == "tool_calls":
                if not tool_calls or tool_call_count + len(tool_calls) > MAX_TOOL_CALLS:
                    break
                if any(not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call["id"] for call in tool_calls):
                    break
                tool_call_count += len(tool_calls)
                assistant_message = {"role": "assistant"}
                if message.get("content") is not None:
                    assistant_message["content"] = message["content"]
                assistant_message["tool_calls"] = tool_calls
                messages.append(assistant_message)
                for call in tool_calls:
                    function = call.get("function", {}) if isinstance(call, dict) else {}
                    name = function.get("name", "")
                    raw_args = function.get("arguments") or "{}"
                    if isinstance(raw_args, dict):
                        raw_args = json.dumps(raw_args, ensure_ascii=False)
                    call_id = call.get("id") if isinstance(call, dict) else None
                    try:
                        result = self._execute_model_tool(name, raw_args, case)
                        if name == "verificar_medicamento_sus" and not result["disponivel_sus"]:
                            force_review = True
                        if name == "checar_contraindicacao" and result["contraindicado"]:
                            force_review = True
                        trace.append(ToolTrace(name, json.loads(raw_args), result, "llm", True))
                        content = json.dumps(result, ensure_ascii=False, allow_nan=False)
                    except (ValueError, TypeError, json.JSONDecodeError, ValidationError, KeyError):
                        error = {"erro_validacao": "argumentos rejeitados pela validação local", "ferramenta_executada": False}
                        trace.append(ToolTrace(name, {}, error, "llm", False))
                        content = json.dumps(error, ensure_ascii=False)
                    messages.append({"role": "tool", "tool_call_id": call_id, "content": content})
                continue

            # Se houver tool_calls com outro finish_reason, não executar nenhuma.
            if tool_calls or finish_reason != "stop":
                break

            raw_content = message.get("content") or ""
            if not isinstance(raw_content, str):
                break
            try:
                output = SaidaAgente.model_validate_json(raw_content)
            except (ValidationError, ValueError):
                messages.append({"role": "assistant", "content": raw_content or "{}"})
                messages.append({
                    "role": "user",
                    "content": "A resposta não passou na validação local. Corrija e retorne somente JSON do schema obrigatório; não invente dados.",
                })
                continue

            output = self._enforce_safety_invariants(
                output, case, pa_result, confirmation, risk_result, medication_audits, force_review
            )
            return AgentRun(saida=output, ferramentas=trace, fluxo_abortado=False)

        run = self._fallback(
            case,
            reason=f"O loop não convergiu em até {self.max_turnos} turnos; nenhuma saída do modelo foi aceita.",
            risk_result=risk_result,
            missing=self._merge_missing(["resposta JSON validada do agente"], confirmation["faltam_dados"]),
            audits=medication_audits,
        )
        run.ferramentas = trace
        return run

    def _execute_model_tool(self, name: str, raw_arguments: str, case: PacienteHAS) -> dict[str, Any]:
        if name not in _TOOL_MODELS:
            raise ValueError("Nome de ferramenta fora da allowlist.")
        arguments = json.loads(raw_arguments)
        if not isinstance(arguments, dict):
            raise ValueError("Argumentos da ferramenta devem ser objeto JSON.")
        validated = _TOOL_MODELS[name].model_validate(arguments)

        if name == "classificar_pa":
            latest = case.consulta_mais_recente()
            if latest is None or latest.pas is None or latest.pad is None:
                raise ValueError("Não há PAS/PAD completos no caso.")
            if validated.pas != latest.pas or validated.pad != latest.pad:
                raise ValueError("Valores divergentes da aferição documentada; execução bloqueada.")
            return classificar_pa(latest.pas, latest.pad, case.sintomas_atuais or [])

        if name == "estratificar_risco_cardio":
            canonical = self._canonical_risk_args(case)
            for field, value in validated.model_dump(exclude_unset=True).items():
                if value is not None and canonical.get(field) != value:
                    raise ValueError(f"Argumento {field!r} não corresponde a dado documentado; execução bloqueada.")
            return estratificar_risco_cardio(**canonical)

        if name == "verificar_medicamento_sus":
            return verificar_medicamento_sus(validated.medicamento)

        if name == "checar_contraindicacao":
            return checar_contraindicacao(validated.medicamento, self._case_conditions(case), self._case_exams(case))

        raise ValueError("Ferramenta não permitida.")

    def _enforce_safety_invariants(
        self,
        output: SaidaAgente,
        case: PacienteHAS,
        pa_result: dict[str, Any],
        pa_confirmation: dict[str, Any],
        risk_result: dict[str, Any],
        medication_audits: list[MedicamentoVerificado],
        force_review: bool,
    ) -> SaidaAgente:
        # Resultados determinísticos sempre prevalecem sobre o texto do modelo.
        output.caso_id = case.caso_id
        output.risco_cardiovascular = risk_result["risco"]
        output.medicamentos_verificados = medication_audits
        output.situacao_atual = _redact_runtime_labels(output.situacao_atual, self.settings)
        output.detalhe_conduta = _redact_runtime_labels(output.detalhe_conduta, self.settings)
        output.justificativa = _redact_runtime_labels(output.justificativa, self.settings)
        output.dados_faltantes = [_redact_runtime_labels(item, self.settings) for item in output.dados_faltantes]
        if pa_result.get("classificacao") and pa_result["classificacao"] not in output.situacao_atual:
            output.situacao_atual = f"PA mais recente: {pa_result['classificacao']}. {output.situacao_atual}"

        missing = self._merge_missing(
            output.dados_faltantes,
            risk_result.get("faltam_dados", []),
            case.dados_faltantes,
            pa_confirmation.get("faltam_dados", []),
        )
        if not pa_confirmation.get("diagnostico_confirmado"):
            prefix = "Diagnóstico de HAS ainda não confirmado em duas ocasiões distintas. "
            if prefix not in output.situacao_atual:
                output.situacao_atual = prefix + output.situacao_atual
            output.nivel_confianca = "baixo"
            force_review = True
        if risk_result["risco"] == "indeterminado":
            force_review = True
            output.nivel_confianca = "baixo"
            output.detalhe_conduta = (
                "PREVENT indeterminado por ausência de dados obrigatórios; solicitar os dados listados e revisar humanamente. "
                + output.detalhe_conduta
            )
        if any(not item.disponivel_sus or item.contraindicacao for item in medication_audits):
            force_review = True
        if case.status_dados == "incompleto":
            force_review = True
        generated_text = " ".join((output.situacao_atual, output.detalhe_conduta, output.justificativa))
        if _menciona_farmaco(generated_text):
            force_review = True
            output.nivel_confianca = "baixo"
            output.situacao_atual = "Menção farmacológica livre bloqueada pelo guardrail; revisar o caso com profissional."
            output.detalhe_conduta = "Revisar qualquer decisão farmacológica com profissional; o agente não prescreve nem recomenda fármaco não verificado."
            output.justificativa = "O backend suprimiu texto com possível nome de medicamento; conferir a lista SUS/PCDT vigente e as contraindicações localmente."

        output.dados_faltantes = missing
        if force_review:
            output.necessita_revisao_humana = True
            if output.conduta_sugerida != "encaminhar_especialista":
                output.conduta_sugerida = "revisao_humana_necessaria"
        return output
