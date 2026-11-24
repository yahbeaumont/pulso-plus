"""PREVENT-CVD de 10 anos (modelo-base), port Python determinístico.

A Diretriz Brasileira de Hipertensão 2025 descreve o PREVENT como estimativa de
risco de desenvolver doença cardiovascular (DCV) em 10 e 30 anos. Esta função
implementa a equação-base de DCV total em 10 anos, não somente ASCVD.

O resultado não constitui validação/calibração brasileira. PREVENT foi
validado em população dos EUA; a DBHA 2025 alerta que escores internacionais
podem ser menos precisos na população brasileira.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .schemas import RiskToolArgs


@dataclass(frozen=True)
class _Coeficientes:
    constante: float
    diabetes: float
    tabagismo: float
    anti_hipertensivo: float
    estatina: float
    idade: float
    colesterol_total_nao_hdl: float
    hdl: float
    pas_baixa: float
    pas_alta: float
    egfr_baixa: float
    egfr_alta: float
    interacao_anti_hipertensivo_pas: float
    interacao_estatina_colesterol: float
    interacao_idade_colesterol: float
    interacao_idade_hdl: float
    interacao_idade_pas: float
    interacao_diabetes_idade: float
    interacao_tabagismo_idade: float
    interacao_idade_egfr: float


# Coeficientes da equação-base PREVENT-CVD de 10 anos, por sexo.
# Transformações e coeficientes portados da implementação pública PyPREVENT
# 0.1.6 (Lars Hegstrom, MIT), módulo cvd; ver THIRD_PARTY_NOTICES.md.
_COEF = {
    "F": _Coeficientes(
        constante=-3.307728,
        diabetes=0.8667604,
        tabagismo=0.5360739,
        anti_hipertensivo=0.3151672,
        estatina=-0.1477655,
        idade=0.7939329,
        colesterol_total_nao_hdl=0.0305239,
        hdl=-0.1606857,
        pas_baixa=-0.2394003,
        pas_alta=0.3600781,
        egfr_baixa=0.6045917,
        egfr_alta=0.0433769,
        interacao_anti_hipertensivo_pas=-0.0663612,
        interacao_estatina_colesterol=0.1197879,
        interacao_idade_colesterol=-0.0819715,
        interacao_idade_hdl=0.0306769,
        interacao_idade_pas=-0.0946348,
        interacao_diabetes_idade=-0.27057,
        interacao_tabagismo_idade=-0.078715,
        interacao_idade_egfr=-0.1637806,
    ),
    "M": _Coeficientes(
        constante=-3.031168,
        diabetes=0.7692857,
        tabagismo=0.4386871,
        anti_hipertensivo=0.288879,
        estatina=-0.1337349,
        idade=0.7688528,
        colesterol_total_nao_hdl=0.0736174,
        hdl=-0.0954431,
        pas_baixa=-0.4347345,
        pas_alta=0.3362658,
        egfr_baixa=0.5378979,
        egfr_alta=0.0164827,
        interacao_anti_hipertensivo_pas=-0.0475924,
        interacao_estatina_colesterol=0.150273,
        interacao_idade_colesterol=-0.0517874,
        interacao_idade_hdl=0.0191169,
        interacao_idade_pas=-0.1049477,
        interacao_diabetes_idade=-0.2251948,
        interacao_tabagismo_idade=-0.0895067,
        interacao_idade_egfr=-0.1543702,
    ),
}

_MISSING_LABELS = (
    ("idade", "idade"),
    ("sexo", "sexo"),
    ("pas", "PAS"),
    ("colesterol_total", "colesterol_total"),
    ("hdl", "HDL"),
    ("diabetes", "diabetes"),
    ("tabagismo", "tabagismo_atual"),
    ("imc", "IMC"),
    ("drfg_estimada", "eGFR"),
    ("em_uso_anti_hipertensivo", "uso_de_anti_hipertensivo"),
    ("em_uso_estatina", "uso_de_estatina"),
    ("doenca_cardiovascular_previa", "histórico_de_DCV_prévia_para_elegibilidade"),
)

_RANGES = (
    ("idade", 30, 79, "idade", "anos"),
    ("colesterol_total", 130, 320, "colesterol_total", "mg/dL"),
    ("hdl", 20, 100, "HDL", "mg/dL"),
    ("pas", 90, 200, "PAS", "mmHg"),
    ("imc", 18.5, 39.9, "IMC", "kg/m²"),
    ("drfg_estimada", 15, 140, "eGFR", "mL/min/1,73 m²"),
)

_AVISO_POPULACIONAL = (
    "PREVENT foi derivado/validado em adultos dos EUA; não foi calibrado para a população brasileira. "
    "Usar como apoio e com revisão profissional, conforme a Diretriz Brasileira de Hipertensão 2025."
)


def _linear_predictor(args: RiskToolArgs) -> float:
    c = _COEF[args.sexo]
    age = float(args.idade)
    total_chol = float(args.colesterol_total)
    hdl = float(args.hdl)
    sbp = float(args.pas)
    egfr = float(args.drfg_estimada)
    diabetes = bool(args.diabetes)
    smoker = bool(args.tabagismo)
    bp_treated = bool(args.em_uso_anti_hipertensivo)
    statin = bool(args.em_uso_estatina)

    age_adj = (age - 55.0) / 10.0
    cholesterol_diff = total_chol - hdl
    cholesterol_diff_adj = 0.02586 * cholesterol_diff - 3.5
    hdl_diff_adj = (0.02586 * hdl - 1.3) / 0.3
    sbp_adj_min = (min(sbp, 110.0) - 110.0) / 20.0
    sbp_adj_max = (max(sbp, 110.0) - 130.0) / 20.0
    egfr_adj_min = (min(egfr, 60.0) - 60.0) / -15.0
    egfr_adj_max = (max(egfr, 60.0) - 90.0) / -15.0

    # IMC é um dado obrigatório do contrato PREVENT; não tem contribuição na
    # equação-base PREVENT-CVD nesta implementação de coeficientes.
    return sum(
        (
            c.constante,
            c.idade * age_adj,
            c.colesterol_total_nao_hdl * cholesterol_diff_adj,
            c.hdl * hdl_diff_adj,
            c.pas_baixa * sbp_adj_min,
            c.pas_alta * sbp_adj_max,
            c.diabetes if diabetes else 0.0,
            c.tabagismo if smoker else 0.0,
            c.egfr_baixa * egfr_adj_min,
            c.egfr_alta * egfr_adj_max,
            c.anti_hipertensivo if bp_treated else 0.0,
            c.estatina if statin else 0.0,
            c.interacao_anti_hipertensivo_pas * sbp_adj_max if bp_treated else 0.0,
            c.interacao_estatina_colesterol * cholesterol_diff_adj if statin else 0.0,
            c.interacao_idade_colesterol * age_adj * cholesterol_diff_adj,
            c.interacao_idade_hdl * age_adj * hdl_diff_adj,
            c.interacao_idade_pas * age_adj * sbp_adj_max,
            c.interacao_diabetes_idade * age_adj if diabetes else 0.0,
            c.interacao_tabagismo_idade * age_adj if smoker else 0.0,
            c.interacao_idade_egfr * age_adj * egfr_adj_min,
        )
    )


def _sigmoid_percent(linear_predictor: float) -> float:
    # Sigmoid estável numericamente para evitar overflow.
    if linear_predictor >= 0:
        probability = 1.0 / (1.0 + math.exp(-linear_predictor))
    else:
        exp_value = math.exp(linear_predictor)
        probability = exp_value / (1.0 + exp_value)
    return probability * 100.0


def _indeterminado(
    *, faltam: list[str] | None = None, invalidos: list[str] | None = None, motivo: str
) -> dict[str, Any]:
    return {
        "risco": "indeterminado",
        "risco_percentual_10_anos": None,
        "modelo": "PREVENT-CVD-10y-base",
        "faltam_dados": faltam or [],
        "dados_invalidos": invalidos or [],
        "motivo": motivo,
        "aviso": _AVISO_POPULACIONAL,
    }


def estratificar_risco_cardio(**dados: Any) -> dict[str, Any]:
    """Calcula PREVENT-CVD de 10 anos ou retorna indeterminado sem imputar.

    Todas as variáveis clínicas obrigatórias precisam ser fornecidas. A história
    prévia de doença cardiovascular é solicitada como critério de elegibilidade:
    PREVENT é uma equação de prevenção primária.
    """
    args = RiskToolArgs.model_validate(dados)
    faltam = [label for field, label in _MISSING_LABELS if getattr(args, field) is None]
    if faltam:
        return _indeterminado(
            faltam=faltam,
            motivo="Não foi calculado: faltam entradas obrigatórias do PREVENT ou confirmação de elegibilidade.",
        )

    if args.doenca_cardiovascular_previa:
        return _indeterminado(
            motivo="PREVENT não deve ser aplicado como estimativa de prevenção primária quando há doença cardiovascular prévia.",
            invalidos=["doenca_cardiovascular_previa=True"],
        )

    invalidos: list[str] = []
    for field, lower, upper, label, unit in _RANGES:
        value = getattr(args, field)
        if value < lower or value > upper:
            invalidos.append(f"{label}={value:g} {unit}; faixa aceita {lower:g}–{upper:g} {unit}")
    if invalidos:
        return _indeterminado(
            invalidos=invalidos,
            motivo="Não foi calculado: um ou mais valores estão fora das faixas operacionais do modelo.",
        )

    raw_percent = _sigmoid_percent(_linear_predictor(args))
    if raw_percent < 5.0:
        category = "baixo"
    elif raw_percent < 7.5:
        category = "limitrofe"
    elif raw_percent < 20.0:
        category = "intermediario"
    else:
        category = "alto"

    return {
        "risco": category,
        "risco_percentual_10_anos": round(raw_percent, 2),
        "modelo": "PREVENT-CVD-10y-base",
        "faltam_dados": [],
        "dados_invalidos": [],
        "motivo": "Estimativa de PREVENT-CVD em 10 anos; não é diagnóstico nem prescrição.",
        "aviso": _AVISO_POPULACIONAL,
    }
