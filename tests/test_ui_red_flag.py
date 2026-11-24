from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import date

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from has_cdss.agent import ClinicalAgent  # noqa: E402
from has_cdss.llm_client import LLMHttpClient  # noqa: E402


class TestUIClinicalForm(unittest.TestCase):
    def _open_demo(self) -> AppTest:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        self.assertFalse(app.exception)
        app.button(key="pulso_demo_login").click().run()
        self.assertFalse(app.exception)
        return app

    def test_campos_clinicos_vazios_sem_inventar_valores_ou_expor_json(self) -> None:
        app = self._open_demo()
        self.assertIsNone(app.session_state["patient_form_age"])
        self.assertIsNone(app.session_state["patient_form_egfr"])
        self.assertIsNone(app.session_state["patient_form_imc"])
        self.assertNotIn("case_json_editor", app.session_state)
        self.assertFalse(any(widget.key == "case_json_editor" for widget in app.text_area))
        self.assertTrue(any(widget.label == "Validar e analisar" for widget in app.button))

    def test_form_monta_paciente_pydantic_com_campos_editados_sem_chamar_motor(self) -> None:
        app = self._open_demo()
        app.number_input(key="patient_form_age").set_value(58)
        app.selectbox(key="patient_form_sex").select("Feminino")
        app.date_input(key="patient_form_pa1_date").set_value(date(2026, 1, 10))
        app.number_input(key="patient_form_pas1").set_value(152)
        app.number_input(key="patient_form_pad1").set_value(96)
        app.date_input(key="patient_form_pa2_date").set_value(date(2026, 2, 14))
        app.number_input(key="patient_form_pas2").set_value(148)
        app.number_input(key="patient_form_pad2").set_value(92)
        app.number_input(key="patient_form_creatinina").set_value(0.9)
        app.number_input(key="patient_form_colesterol_total").set_value(180)
        app.number_input(key="patient_form_hdl").set_value(50)
        app.number_input(key="patient_form_egfr").set_value(90)
        app.number_input(key="patient_form_imc").set_value(25.0)
        app.selectbox(key="patient_form_diabetes").select("Não")
        app.selectbox(key="patient_form_smoking").select("Não")
        app.selectbox(key="patient_form_antihypertensive").select("Não")
        app.selectbox(key="patient_form_statin").select("Não")
        app.selectbox(key="patient_form_prior_cvd").select("Não")
        app.checkbox(key="patient_form_no_medicines").set_value(True)
        app.checkbox(key="patient_form_confirm_reviewed").set_value(True)

        captured = []

        def capture_case(_agent: ClinicalAgent, case: object) -> None:
            captured.append(case)
            raise RuntimeError("No network in UI mapping test")

        with patch.object(ClinicalAgent, "analyze", autospec=True, side_effect=capture_case):
            app.button(key="pulso_submit_case").click().run()

        self.assertFalse(app.exception)
        self.assertEqual(len(captured), 1)
        case = captured[0]
        self.assertEqual(case.idade, 58)
        self.assertEqual(case.sexo, "F")
        self.assertEqual(len(case.consultas), 2)
        self.assertNotEqual(case.consultas[0].data, case.consultas[1].data)
        self.assertEqual((case.consultas[0].pas, case.consultas[0].pad), (152, 96))
        self.assertEqual(case.exames_recentes.drfg_estimada, 90)
        self.assertEqual(case.exames_recentes.imc, 25.0)
        self.assertFalse(case.tabagismo_atual)
        self.assertFalse(case.em_uso_estatina)
        self.assertEqual(case.medicamentos_em_uso, [])

    def test_troponina_colada_autopreenche_formulario_e_aborta_antes_do_motor(self) -> None:
        synthetic_note = (
            "Idade: 58 anos\nSexo: Feminino\nPA: 152/96\n"
            "Troponina 2.5\nSintomas atuais: dor torácica"
        )
        app = self._open_demo()
        app.text_area(key="record_text_input").set_value(synthetic_note)
        app.button(key="FormSubmitter:pulso_record_form-Extrair campos para revisão").click().run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["patient_form_age"], 58)
        self.assertEqual(app.session_state["patient_form_sex"], "Feminino")
        self.assertEqual(app.session_state["patient_form_pas1"], 152)
        self.assertEqual(app.session_state["patient_form_pad1"], 96)
        self.assertEqual(app.session_state["patient_form_troponina"], 2.5)
        self.assertIsNone(app.session_state["patient_form_egfr"])
        self.assertNotIn("case_json_editor", app.session_state)

        app.checkbox(key="patient_form_confirm_reviewed").set_value(True)
        with patch.object(LLMHttpClient, "create", side_effect=AssertionError("HTTP must not be called")):
            app.button(key="pulso_submit_case").click().run()

        self.assertFalse(app.exception)
        run = app.session_state["analysis_run"]
        self.assertTrue(run.fluxo_abortado)
        self.assertEqual(run.saida.conduta_sugerida, "encaminhar_especialista")
        self.assertTrue(run.saida.necessita_revisao_humana)
        self.assertEqual(len(run.ferramentas), 1)
        self.assertEqual(run.ferramentas[0].nome, "verificar_red_flags_infarto")
        self.assertTrue(run.ferramentas[0].resultado["alerta_vermelho"])

        app.button(key="pulso_clear_case").click().run()
        self.assertFalse(app.exception)
        self.assertIsNone(app.session_state["patient_form_age"])
        self.assertIsNone(app.session_state["patient_form_troponina"])
        self.assertEqual(app.session_state["patient_form_symptoms"], "")
        self.assertFalse(app.session_state["patient_form_confirm_reviewed"])
        self.assertNotIn("candidate_case", app.session_state)
        self.assertNotIn("analysis_run", app.session_state)


if __name__ == "__main__":
    unittest.main()
