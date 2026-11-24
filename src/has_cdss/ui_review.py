from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def patient_form_fingerprint(state: Mapping[str, Any]) -> str:
    values = {key: value for key, value in state.items() if isinstance(key, str) and key.startswith("patient_form_")}
    payload = json.dumps(values, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def suggestion_can_be_acknowledged(run: Any) -> bool:
    if run is None or run.fluxo_abortado:
        return False
    output = run.saida
    preflight = {trace.nome: trace for trace in run.ferramentas if trace.origem == "preflight" and trace.executada}
    required = {"verificar_red_flags_infarto", "classificar_pa", "verificar_confirmacao_pa", "estratificar_risco_cardio"}
    if not required.issubset(preflight):
        return False
    if not preflight["verificar_confirmacao_pa"].resultado.get("diagnostico_confirmado"):
        return False
    if preflight["verificar_red_flags_infarto"].resultado.get("bloquear_fluxo_hipertensao"):
        return False
    checked = [trace.argumentos.get("medicamento") for trace in run.ferramentas if trace.nome == "verificar_medicamento_sus" and trace.origem == "preflight" and trace.executada]
    if sorted(checked) != sorted(med.nome for med in output.medicamentos_verificados):
        return False
    contraindications = [trace.argumentos.get("medicamento") for trace in run.ferramentas if trace.nome == "checar_contraindicacao" and trace.origem == "preflight" and trace.executada]
    if sorted(checked) != sorted(contraindications):
        return False
    if output.conduta_sugerida in {"ajustar_dose", "trocar_classe", "adicionar_segunda_classe"} and not checked:
        return False
    return (
        not output.necessita_revisao_humana
        and not output.dados_faltantes
        and output.risco_cardiovascular != "indeterminado"
        and output.conduta_sugerida in {"manter", "ajustar_dose", "adicionar_segunda_classe", "trocar_classe"}
        and not any(trace.resultado.get("alerta_vermelho") for trace in run.ferramentas)
        and all(med.disponivel_sus and not med.contraindicacao for med in output.medicamentos_verificados)
    )


def suggestion_fingerprint(run: Any) -> str:
    payload = json.dumps(run.saida.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
