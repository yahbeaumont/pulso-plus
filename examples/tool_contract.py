"""A clinical tool as a typed function.

The model chooses when to call it and with which arguments. It never computes
the result. Returning a model instead of a sentence is what lets the interface
render the trail as data and lets the guardrails compare the model's text
against what the tool actually produced.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Stage(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    STAGE_1 = "stage_1"
    STAGE_2 = "stage_2"
    STAGE_3 = "stage_3"


class Reading(BaseModel):
    systolic: int = Field(ge=60, le=300)
    diastolic: int = Field(ge=30, le=200)
    context: str = "consultation"

    @model_validator(mode="after")
    def systolic_above_diastolic(self) -> "Reading":
        if self.systolic <= self.diastolic:
            raise ValueError("systolic must exceed diastolic")
        return self


class Classification(BaseModel):
    stage: Stage
    label: str
    reference: str
    confirmed: bool


def classify_pressure(reading: Reading, confirmed: bool = False) -> Classification:
    """Map one reading to a stage. The thresholds live here, not in the prompt."""
    systolic, diastolic = reading.systolic, reading.diastolic
    if systolic >= 180 or diastolic >= 110:
        stage, label = Stage.STAGE_3, "hipertensao estagio 3"
    elif systolic >= 160 or diastolic >= 100:
        stage, label = Stage.STAGE_2, "hipertensao estagio 2"
    elif systolic >= 140 or diastolic >= 90:
        stage, label = Stage.STAGE_1, "hipertensao estagio 1"
    elif systolic >= 130 or diastolic >= 85:
        stage, label = Stage.ELEVATED, "pressao elevada"
    else:
        stage, label = Stage.NORMAL, "pressao normal"
    return Classification(
        stage=stage,
        label=label,
        reference="Diretriz Brasileira de Hipertensao Arterial, PCDT-MS 2025",
        confirmed=confirmed,
    )


if __name__ == "__main__":
    result = classify_pressure(Reading(systolic=145, diastolic=95))
    print(result.model_dump_json(indent=2))
