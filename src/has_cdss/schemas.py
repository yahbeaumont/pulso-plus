from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictBool, StrictInt, field_validator


def _strict_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("O valor precisa ser numérico; coerção de texto não é permitida.")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError("O valor precisa ser finito.")
    return number


StrictNumber = Annotated[float, BeforeValidator(_strict_number)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Consulta(StrictModel):
    data: date | None = None
    pas: StrictInt | None = None
    pad: StrictInt | None = None


class MedicamentoEmUso(StrictModel):
    nome: str = Field(min_length=1, max_length=100)
    dose: str | None = None
    frequencia: str | None = None


class ExamesRecentes(StrictModel):
    """Campos clínicos explicitamente autorizados; exames extras são rejeitados."""

    colesterol_total: StrictNumber | None = None
    hdl: StrictNumber | None = None
    drfg_estimada: StrictNumber | None = None
    imc: StrictNumber | None = None
    potassio: StrictNumber | None = None
    creatinina: StrictNumber | None = None
    hba1c: StrictNumber | None = None
    troponina: StrictNumber | None = None
    ckmb: StrictNumber | None = None
    ckmb_limite_superior: StrictNumber | None = None

    @field_validator("troponina", "ckmb", "ckmb_limite_superior")
    @classmethod
    def biomarcadores_nao_negativos(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("Biomarcador e limite de referência não podem ser negativos.")
        return value


class RiskToolArgs(StrictModel):
    """Argumentos parciais são aceitos para que a ferramenta enumere dados ausentes."""

    idade: StrictInt | None = None
    sexo: Literal["M", "F"] | None = None
    pas: StrictNumber | None = None
    colesterol_total: StrictNumber | None = None
    hdl: StrictNumber | None = None
    diabetes: StrictBool | None = None
    tabagismo: StrictBool | None = None
    imc: StrictNumber | None = None
    drfg_estimada: StrictNumber | None = None
    em_uso_anti_hipertensivo: StrictBool | None = None
    em_uso_estatina: StrictBool | None = None
    doenca_cardiovascular_previa: StrictBool | None = None


class ClassificarPAArgs(StrictModel):
    pas: StrictInt
    pad: StrictInt
    sintomas: list[str] = Field(default_factory=list)


class VerificarMedicamentoArgs(StrictModel):
    medicamento: str = Field(min_length=1, max_length=100)


class ContraindicacaoArgs(StrictModel):
    medicamento: str = Field(min_length=1, max_length=100)
    condicoes: list[str] = Field(default_factory=list)
    exames: dict[str, Any] = Field(default_factory=dict)


class PacienteHAS(StrictModel):
    caso_id: str = Field(min_length=1, max_length=100)
    idade: StrictInt | None = None
    sexo: Literal["M", "F"] | None = None
    consultas: list[Consulta] = Field(default_factory=list)
    medicamentos_em_uso: list[MedicamentoEmUso] | None = None
    comorbidades: list[str] = Field(default_factory=list)
    exames_recentes: ExamesRecentes = Field(default_factory=ExamesRecentes)
    sintomas_atuais: list[str] | None = None
    observacoes: str = ""

    # Entradas explícitas exigidas pelo PREVENT ou pela regra de elegibilidade.
    diabetes: StrictBool | None = None
    tabagismo_atual: StrictBool | None = None
    em_uso_anti_hipertensivo: StrictBool | None = None
    em_uso_estatina: StrictBool | None = None
    doenca_cardiovascular_previa: StrictBool | None = None
    gestante: StrictBool | None = None
    suspeita_hipertensao_secundaria: StrictBool | None = None

    # Campos do conversor de CSV: sinalizam ausência sem criar medidas fictícias.
    status_dados: Literal["completo", "incompleto"] = "completo"
    dados_faltantes: list[str] = Field(default_factory=list)

    @field_validator("caso_id")
    @classmethod
    def case_id_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("caso_id não pode ser vazio.")
        return value

    def consulta_mais_recente(self) -> Consulta | None:
        if not self.consultas:
            return None
        # Uma consulta sem data no fim da lista pode ser a mais recente; não
        # recuar silenciosamente para uma aferição antiga que esteja completa.
        if self.consultas[-1].data is None:
            return self.consultas[-1]
        dated = [consulta for consulta in self.consultas if consulta.data is not None]
        if dated:
            return max(dated, key=lambda consulta: consulta.data)
        return self.consultas[-1]


class MedicamentoVerificado(StrictModel):
    nome: str
    disponivel_sus: StrictBool
    contraindicacao: StrictBool


class SaidaAgente(StrictModel):
    caso_id: str
    situacao_atual: str
    risco_cardiovascular: Literal["indeterminado", "baixo", "limitrofe", "intermediario", "alto"]
    conduta_sugerida: Literal[
        "manter",
        "ajustar_dose",
        "adicionar_segunda_classe",
        "trocar_classe",
        "encaminhar_especialista",
        "revisao_humana_necessaria",
    ]
    detalhe_conduta: str
    justificativa: str
    medicamentos_verificados: list[MedicamentoVerificado] = Field(default_factory=list)
    nivel_confianca: Literal["baixo", "medio", "alto"]
    necessita_revisao_humana: StrictBool
    dados_faltantes: list[str] = Field(default_factory=list)
