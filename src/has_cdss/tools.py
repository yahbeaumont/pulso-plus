from __future__ import annotations

import re
import unicodedata
from typing import Any

from .prevent import estratificar_risco_cardio


# Allowlist MVP baseada no arquivo RENAME 2024 compartilhado no projeto e nos
# medicamentos mínimos do briefing inicial. Isso não substitui a conferência da
# edição RENAME/PCDT 2025 nem confirma disponibilidade municipal.
MEDICAMENTOS_SUS = {
    "losartana": {"losartana", "losartana potassica"},
    "enalapril": {"enalapril", "maleato de enalapril"},
    "captopril": {"captopril"},
    "anlodipino": {"anlodipino", "amlodipino"},
    "nifedipino": {"nifedipino"},
    "hidroclorotiazida": {"hidroclorotiazida", "hctz"},
    # Consta no escopo inicial do projeto; não aparece no arquivo local RENAME 2024.
    "clortalidona": {"clortalidona"},
    "furosemida": {"furosemida"},
    "atenolol": {"atenolol"},
    "carvedilol": {"carvedilol"},
    "metoprolol": {"metoprolol", "succinato de metoprolol", "tartarato de metoprolol"},
    "propranolol": {"propranolol", "cloridrato de propranolol"},
    "espironolactona": {"espironolactona"},
    "hidralazina": {"hidralazina", "cloridrato de hidralazina"},
    "verapamil": {"verapamil", "cloridrato de verapamil"},
    "doxazosina": {"doxazosina", "mesilato de doxazosina"},
    "metildopa": {"metildopa"},
}

IECA = {"enalapril", "captopril"}
TIAZIDICOS = {"hidroclorotiazida", "clortalidona"}
BETABLOQUEADORES = {"atenolol", "carvedilol", "metoprolol", "propranolol"}

SINTOMAS_LESao_ORGAO_ALVO = {
    "dor toracica",
    "dor no peito",
    "dispneia",
    "falta de ar",
    "deficit neurologico",
    "fraqueza de um lado",
    "alteracao visual",
    "visao turva",
    "confusao",
    "rebaixamento do nivel de consciencia",
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", texto).strip()


def _normalizar_nome_medicamento(texto: str) -> str:
    value = _normalizar(texto)
    # Remove concentração e apresentação que podem acompanhar o nome genérico.
    value = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:mg|mcg|ug|g|ui|ml|%)\b.*$", "", value)
    value = re.sub(r"\b(comprimido|capsula|solucao|injetavel|liberacao prolongada)\b", " ", value)
    for salt in ("cloridrato de ", "maleato de ", "mesilato de ", "succinato de ", "tartarato de "):
        value = value.replace(salt, "")
    value = value.replace(" potassica", "")
    return re.sub(r"\s+", " ", value).strip()


def _sintoma_positivo(text: str, expected: str) -> bool:
    start = text.find(expected)
    if start < 0:
        return False
    prefix = text[max(0, start - 32):start]
    negations = (
        "sem ",
        "nega ",
        "nega a presenca de ",
        "ausencia de ",
        "nao apresenta ",
        "sem queixa de ",
    )
    return not any(prefix.endswith(negation) for negation in negations)


def _classificacao_por_faixas(pas: int, pad: int) -> str:
    if pas >= 180 or pad >= 110:
        return "HAS estágio 3"
    if pas >= 160 or pad >= 100:
        return "HAS estágio 2"
    if pas >= 140 or pad >= 90:
        return "HAS estágio 1"
    if pas >= 120 or pad >= 80:
        return "pré-hipertensão"
    return "normal"


def classificar_pa(
    pas: int | None,
    pad: int | None,
    sintomas: list[str] | None = None,
) -> dict[str, Any]:
    """Classifica PA segundo as faixas do briefing e falha fechado sem PAS/PAD."""
    faltam = []
    if pas is None:
        faltam.append("PAS")
    if pad is None:
        faltam.append("PAD")
    if faltam:
        return {
            "classificacao": "indeterminada",
            "status_dados": "incompleto",
            "faltam_dados": faltam,
            "alerta": None,
        }
    if isinstance(pas, bool) or isinstance(pad, bool) or not isinstance(pas, int) or not isinstance(pad, int):
        raise ValueError("PAS e PAD precisam ser inteiros em mmHg.")
    if not (40 <= pas <= 300 and 20 <= pad <= 200):
        raise ValueError("PAS/PAD fora dos limites operacionais aceitos para aferição.")
    if pas <= pad:
        raise ValueError("PAS precisa ser maior que PAD; conferir a aferição registrada.")

    classificacao = _classificacao_por_faixas(pas, pad)
    symptoms_norm = [_normalizar(item) for item in (sintomas or []) if _normalizar(item)]
    symptom_target = any(
        _sintoma_positivo(symptom, expected)
        for symptom in symptoms_norm
        for expected in SINTOMAS_LESao_ORGAO_ALVO
    )
    emergency = (pas >= 180 or pad >= 110) and symptom_target
    return {
        "classificacao": classificacao,
        "status_dados": "completo",
        "pas": pas,
        "pad": pad,
        "alerta": "emergencia_hipertensiva" if emergency else None,
        "sintomas_lesao_orgao_alvo": symptom_target,
    }


def verificar_confirmacao_pa(consultas: list[dict[str, Any]]) -> dict[str, Any]:
    """Confirma registro de PA completa em duas datas distintas, sem inferir ocasiões."""
    completas = [
        item for item in consultas
        if item.get("pas") is not None and item.get("pad") is not None
    ]
    validas = []
    invalidas = 0
    for item in completas:
        try:
            result = classificar_pa(item["pas"], item["pad"])
        except (TypeError, ValueError):
            invalidas += 1
            continue
        if result.get("status_dados") == "completo":
            validas.append(item)
    datas_distintas = {
        str(item.get("data"))
        for item in validas
        if item.get("data") is not None and str(item.get("data")).strip()
    }
    confirmado = len(datas_distintas) >= 2
    faltam = [] if confirmado else ["segunda_afericao_confirmatoria_em_ocasiao_distinta"]
    if len(validas) >= 2 and len(datas_distintas) < 2:
        faltam = ["datas_de_afericoes_em_ocasioes_distintas"]
    return {
        "diagnostico_confirmado": confirmado,
        "afericoes_completas": len(completas),
        "afericoes_validas": len(validas),
        "afericoes_invalidas": invalidas,
        "ocasioes_com_data_distinta": len(datas_distintas),
        "faltam_dados": faltam,
    }


def verificar_medicamento_sus(medicamento: str) -> dict[str, Any]:
    normalized = _normalizar_nome_medicamento(medicamento)
    canonical = None
    for name, aliases in MEDICAMENTOS_SUS.items():
        normalized_aliases = {_normalizar_nome_medicamento(alias) for alias in aliases}
        if normalized in normalized_aliases:
            canonical = name
            break
    return {
        "medicamento": medicamento,
        "nome_canonico": canonical,
        "disponivel_sus": canonical is not None,
        "fonte_lista": "allowlist MVP: RENAME 2024 compartilhada + escopo inicial; confirmar edição 2025 e elenco local",
    }


def checar_contraindicacao(
    medicamento: str,
    condicoes: list[str] | None = None,
    exames: dict[str, Any] | None = None,
) -> dict[str, Any]:
    canonical_result = verificar_medicamento_sus(medicamento)
    canonical = canonical_result["nome_canonico"] or _normalizar_nome_medicamento(medicamento)
    conditions = [_normalizar(item) for item in (condicoes or [])]
    condition_text = " | ".join(conditions)
    exams = exames or {}

    if canonical in IECA and any(term in condition_text for term in ("gestacao", "gravidez", "gestante")):
        return {"contraindicado": True, "motivo": "IECA não deve ser usado na gestação.", "alerta": None}
    if canonical in IECA and "estenose bilateral" in condition_text and "renal" in condition_text:
        return {"contraindicado": True, "motivo": "IECA contraindicado em estenose bilateral de artérias renais.", "alerta": None}

    if canonical in TIAZIDICOS:
        potassium = exams.get("potassio")
        if isinstance(potassium, (int, float)) and not isinstance(potassium, bool) and potassium < 3.0:
            return {"contraindicado": True, "motivo": "Potássio abaixo de 3,0 mEq/L; requer revisão antes de considerar tiazídico.", "alerta": None}

    if canonical in BETABLOQUEADORES and "asma" in condition_text:
        return {
            "contraindicado": False,
            "motivo": "Asma registrada: betabloqueador não é primeira escolha neste contexto; revisar individualmente.",
            "alerta": "cautela_clinica",
        }
    return {"contraindicado": False, "motivo": "Nenhuma contraindicação mínima identificada com os dados fornecidos.", "alerta": None}


def verificar_red_flags_infarto(
    troponina: float | None,
    ckmb: float | None,
    ckmb_limite_superior: float | None = None,
) -> dict[str, Any]:
    """Safety net: troponina >0,04 ou CK-MB acima do limite do próprio laboratório.

    O limite superior do CK-MB deve vir do laboratório/caso. Sem referência
    laboratorial, qualquer CK-MB recebido bloqueia a análise de HAS e pede revisão
    urgente, mas não é rotulado automaticamente como infarto.
    """
    triggers: list[str] = []
    if troponina is not None and troponina > 0.04:
        triggers.append("troponina_acima_de_0.04")
    if ckmb is not None and ckmb_limite_superior is not None and ckmb > ckmb_limite_superior:
        triggers.append("ckmb_acima_do_limite_laboratorial")

    if triggers:
        return {
            "alerta_vermelho": True,
            "bloquear_fluxo_hipertensao": True,
            "necessita_revisao_humana": True,
            "conduta": "encaminhar_especialista",
            "triggers": triggers,
            "motivo": "Biomarcador acima do limiar configurado; interromper o fluxo de HAS e encaminhar para avaliação urgente. Isto não confirma diagnóstico de infarto.",
        }
    if ckmb is not None and ckmb_limite_superior is None:
        return {
            "alerta_vermelho": False,
            "bloquear_fluxo_hipertensao": True,
            "necessita_revisao_humana": True,
            "conduta": "revisao_humana_necessaria",
            "triggers": ["ckmb_sem_referencia_laboratorial"],
            "motivo": "CK-MB presente sem limite de referência/unidade do laboratório; fluxo de HAS bloqueado até revisão humana.",
        }
    return {
        "alerta_vermelho": False,
        "bloquear_fluxo_hipertensao": False,
        "necessita_revisao_humana": False,
        "conduta": None,
        "triggers": [],
        "motivo": "Nenhum critério de safety net detectado com os biomarcadores fornecidos.",
    }
