"""A refusal that runs before the model is called.

A prompt instruction is followed most of the time. A function is followed every
time, and it can be tested. The test below asserts on the sequence of calls
rather than on the final text, because a system that reaches the right answer
through the wrong path will eventually reach the wrong answer through the right
one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

TROPONIN_LIMIT = 0.04
CKMB_LIMIT = 25.0


@dataclass
class Case:
    age: int
    systolic: int
    diastolic: int
    troponin: float | None = None
    ckmb: float | None = None


@dataclass
class Outcome:
    halted: bool
    reason: str | None = None
    needs_human_review: bool = False
    calls: list[str] = field(default_factory=list)


def preflight(case: Case, engine: Callable[[Case], str]) -> Outcome:
    """Return an emergency outcome, or delegate to the hypertension engine."""
    findings = []
    if case.troponin is not None and case.troponin > TROPONIN_LIMIT:
        findings.append(f"troponina {case.troponin} acima do limite de referencia")
    if case.ckmb is not None and case.ckmb > CKMB_LIMIT:
        findings.append(f"CK-MB {case.ckmb} elevada")

    if findings:
        return Outcome(
            halted=True,
            reason="sinal de sindrome coronariana aguda: " + "; ".join(findings),
            needs_human_review=True,
            calls=["verificar_red_flags_infarto"],
        )

    outcome = Outcome(halted=False, calls=["verificar_red_flags_infarto", "classificar_pa"])
    outcome.reason = engine(case)
    return outcome


def engine(case: Case) -> str:
    return "conduta de hipertensao"


if __name__ == "__main__":
    import unittest

    class PreflightTest(unittest.TestCase):
        def test_raised_troponin_never_reaches_the_engine(self) -> None:
            case = Case(age=58, systolic=150, diastolic=95, troponin=2.5)
            outcome = preflight(case, engine)
            self.assertTrue(outcome.halted)
            self.assertTrue(outcome.needs_human_review)
            self.assertEqual(outcome.calls, ["verificar_red_flags_infarto"])

        def test_clean_case_reaches_the_engine(self) -> None:
            case = Case(age=55, systolic=145, diastolic=95, troponin=0.01, ckmb=8.0)
            outcome = preflight(case, engine)
            self.assertFalse(outcome.halted)
            self.assertIn("classificar_pa", outcome.calls)

    unittest.main(argv=["preflight_gate"], exit=False, verbosity=2)
