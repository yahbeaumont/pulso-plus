from __future__ import annotations

import sys
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from has_cdss.agent import AgentRun, ToolTrace
from has_cdss.schemas import SaidaAgente, MedicamentoVerificado
from has_cdss.ui_review import patient_form_fingerprint, suggestion_can_be_acknowledged


def test_only_output(review=False, missing=None) -> AgentRun:
    # Saída simulada apenas para testar UI, nunca evidência de resultado clínico.
    output = SaidaAgente(caso_id="TEST-UI", situacao_atual="Saída simulada de teste unitário", risco_cardiovascular="baixo", conduta_sugerida="ajustar_dose", detalhe_conduta="Avaliar possível ajuste com profissional.", justificativa="Fixture de UI, sem motor real.", nivel_confianca="medio", necessita_revisao_humana=review, dados_faltantes=missing or [])
    output.medicamentos_verificados = [MedicamentoVerificado(nome="losartana", disponivel_sus=True, contraindicacao=False)]
    traces = [ToolTrace(name, {}, result, "preflight") for name, result in [
        ("verificar_red_flags_infarto", {"bloquear_fluxo_hipertensao":False}),
        ("classificar_pa", {"classificacao":"HAS estágio 1"}),
        ("verificar_confirmacao_pa", {"diagnostico_confirmado":True}),
        ("estratificar_risco_cardio", {"risco":"baixo"}),
    ]]
    traces += [ToolTrace("verificar_medicamento_sus", {"medicamento":"losartana"}, {"disponivel_sus":True}, "preflight"), ToolTrace("checar_contraindicacao", {"medicamento":"losartana"}, {"contraindicado":False}, "preflight")]
    return AgentRun(output, traces, False)


class TestUIReview(unittest.TestCase):
    def open_with_output(self, run):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
        app.button(key="pulso_demo_login").click().run()
        app.session_state["patient_form_confirm_reviewed"] = True
        app.session_state["analysis_run"] = run
        app.session_state["analysis_form_fingerprint"] = patient_form_fingerprint(dict(app.session_state))
        app.run()
        return app

    def test_aceite_exige_revisao_e_e_apenas_da_sessao(self):
        app = self.open_with_output(test_only_output())
        self.assertFalse(app.button(key="pulso_accept_suggestion").disabled)
        app.button(key="pulso_accept_suggestion").click().run()
        self.assertNotIn("suggestion_acknowledged", app.session_state)
        app.checkbox(key="pulso_accept_confirm").set_value(True).run()
        app.button(key="pulso_accept_suggestion").click().run()
        self.assertIn("suggestion_acknowledged", app.session_state)
        app.number_input(key="patient_form_age").set_value(56).run()
        self.assertNotIn("analysis_run", app.session_state)
        self.assertNotIn("suggestion_acknowledged", app.session_state)
        self.assertFalse(app.exception)

    def test_emergencia_revisao_e_dados_faltantes_bloqueiam(self):
        for run in [test_only_output(True), test_only_output(False, ["HDL"])]:
            self.assertFalse(suggestion_can_be_acknowledged(run))
            app = self.open_with_output(run)
            self.assertTrue(app.button(key="pulso_accept_suggestion").disabled)
        emergency = test_only_output()
        emergency.ferramentas.append(ToolTrace("safety", {}, {"alerta_vermelho": True}, "preflight"))
        self.assertFalse(suggestion_can_be_acknowledged(emergency))
        app = self.open_with_output(emergency)
        self.assertTrue(app.button(key="pulso_accept_suggestion").disabled)

    def test_limpar_e_sair_removem_aceite(self):
        for action in ["pulso_clear_case", "logout"]:
            app = self.open_with_output(test_only_output())
            app.checkbox(key="pulso_accept_confirm").set_value(True).run()
            app.button(key="pulso_accept_suggestion").click().run()
            if action == "logout":
                next(button for button in app.button if button.label == "Sair e limpar sessão").click().run()
            else:
                app.button(key=action).click().run()
            self.assertNotIn("suggestion_acknowledged", app.session_state)
            self.assertNotIn("analysis_run", app.session_state)
            self.assertFalse(app.exception)

    def test_confirmacao_retirada_e_trilha_incompleta_bloqueiam(self):
        app = self.open_with_output(test_only_output())
        app.checkbox(key="patient_form_confirm_reviewed").set_value(False).run()
        self.assertNotIn("analysis_run", app.session_state)
        run = test_only_output()
        run.ferramentas = []
        self.assertFalse(suggestion_can_be_acknowledged(run))
        run = test_only_output()
        run.saida.medicamentos_verificados = []
        self.assertFalse(suggestion_can_be_acknowledged(run))

    def test_trocar_configuracao_invalida_resultado_e_aceite(self):
        app = self.open_with_output(test_only_output())
        app.checkbox(key="pulso_accept_confirm").set_value(True).run()
        app.button(key="pulso_accept_suggestion").click().run()
        next(radio for radio in app.radio if radio.label == "Navegação").set_value("Configuração").run()
        app.text_input(key="pulso_api_key_input").set_value("synthetic-test-key")
        app.text_input(key="pulso_base_url_input").set_value("https://example.com/v1")
        app.text_input(key="pulso_model_name_input").set_value("synthetic-test-model")
        next(button for button in app.button if button.label == "Ativar nesta sessão").click().run()
        self.assertFalse(app.exception)
        self.assertNotIn("analysis_run", app.session_state)
        self.assertNotIn("suggestion_acknowledged", app.session_state)


if __name__ == "__main__":
    unittest.main()
