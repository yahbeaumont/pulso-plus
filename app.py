from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from has_cdss.agent import ClinicalAgent, _redact_runtime_labels  # noqa: E402
from has_cdss.auth import verify_local_login  # noqa: E402
from has_cdss.clinical_parser import LocalExtractionError, extract_document_text, parse_clinical_text  # noqa: E402
from has_cdss.config import LLMSettings, get_llm_settings, load_local_environment  # noqa: E402
from has_cdss.llm_client import LLMHttpClient  # noqa: E402
from has_cdss.schemas import PacienteHAS  # noqa: E402
from has_cdss.ui_review import patient_form_fingerprint, suggestion_can_be_acknowledged, suggestion_fingerprint  # noqa: E402

load_local_environment()
st.set_page_config(page_title="Pulso+ | Apoio à decisão clínica", page_icon="+", layout="wide", initial_sidebar_state="auto")

CSS = """
<style>
:root { --navy:#0f2937; --navy-2:#0f172a; --green:#10b981; --green-2:#d1fae5; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --page:#f8fafc; --amber:#92400e; --amber-bg:#fef3c7; --red:#991b1b; --red-bg:#fee2e2; }
html, body, button, input, textarea, select, label, p, h1, h2, h3, h4, code, pre,
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stMarkdownContainer"] * { font-family:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif !important; }
.material-symbols-rounded, [data-testid="stIconMaterial"] { font-family:"Material Symbols Rounded" !important; }
[data-testid="stAppViewContainer"] { background:var(--page); color:var(--ink); }
.block-container { padding-top:1.2rem; padding-bottom:7rem; max-width:1600px; }
[data-testid="stSidebar"] { background:var(--navy); }
[data-testid="stSidebar"] * { color:#eaf0f7 !important; }
[data-testid="stSidebar"] button, [data-testid="stSidebar"] button * { color:var(--navy) !important; }
[data-testid="stSidebar"] [data-testid="stRadio"] label { color:#eaf0f7 !important; }
.pulso-logo { font-size:2rem; font-weight:800; letter-spacing:-1.2px; color:#fff; line-height:1; }
.pulso-logo span { color:var(--green); }
.login-panel .pulso-logo { font-size:3.25rem; }
.login-panel { min-height:650px; padding:56px 46px 34px; border-radius:24px; color:#f8fbff; background:radial-gradient(circle at 100% 0%,#0d3b5c 0,transparent 42%),linear-gradient(145deg,#061a31,#062441 78%); position:relative; overflow:hidden; }
.login-panel:after { content:""; position:absolute; width:620px; height:420px; right:-330px; bottom:-245px; border:1px solid rgba(31,203,154,.28); border-radius:50%; box-shadow:0 0 0 64px rgba(31,203,154,.035),0 0 0 128px rgba(31,203,154,.03); }
.login-panel h1 { margin:68px 0 38px; font-size:clamp(2rem,3.4vw,3.35rem); line-height:1.14; letter-spacing:-1.5px; color:#fff; }
.login-benefit { display:flex; align-items:center; gap:16px; margin:18px 0; color:#dbe5ef; font-size:1.04rem; }
.login-benefit svg { width:27px; height:27px; flex:0 0 27px; stroke:#dbe5ef; fill:none; stroke-width:1.7; }
.ecg { position:absolute; left:0; right:0; bottom:45px; width:100%; height:75px; opacity:.8; }
.st-key-login_right_card { padding:42px clamp(24px,5vw,74px); background:#fff; border:1px solid var(--line); border-radius:24px; min-height:650px; box-shadow:0 8px 24px rgba(13,35,58,.035); }
.st-key-login_right_card h2 { margin:46px 0 8px; font-size:2.3rem; line-height:1.2; color:var(--navy); letter-spacing:-.7px; }
.st-key-login_right_card p { color:#687586; font-size:1.05rem; line-height:1.6; }
.login-footer { margin-top:46px; color:#697587; font-size:.85rem; }
[data-testid="stLayoutWrapper"] > [data-testid="stVerticalBlock"]:has(> [data-testid="stElementContainer"] [data-testid="stMarkdownContainer"] h3) { background:#fff !important; border:1px solid var(--line) !important; border-radius:12px !important; box-shadow:0 4px 16px rgba(15,23,42,.055) !important; }
[data-testid="stMetric"] { background:#f7f9fc; border:1px solid var(--line); border-radius:14px; padding:12px 14px; }
.stButton > button, [data-testid="stFormSubmitButton"] button { border-radius:10px; }
.stButton > button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind^="primary"] { background:var(--green) !important; border-color:var(--green) !important; color:#fff !important; border-radius:11px; font-weight:650; min-height:2.7rem; }
[data-testid="stFormSubmitButton"] button[kind^="primary"] * { color:#fff !important; }
[data-testid="stAlertContentWarning"] { background:#fef3c7 !important; color:#92400e !important; border-radius:12px; }
[data-testid="stAlertContentWarning"] * { color:#92400e !important; }
[data-testid="stAlertContentError"] { background:#fee2e2 !important; color:#991b1b !important; border-radius:12px; }
[data-testid="stAlertContentError"] * { color:#991b1b !important; }
[data-testid="stAlertContentSuccess"] { background:#d1fae5 !important; color:#065f46 !important; border-radius:12px; }
[data-testid="stAlertContentSuccess"] * { color:#065f46 !important; }
.status-green { background:var(--green-2); color:#065f46; border:1px solid #a7f3d0; }
.status-amber { background:var(--amber-bg); color:var(--amber); border:1px solid #f4d491; }
.status-red { background:var(--red-bg); color:var(--red); border:1px solid #f2bac4; }
.status-chip { display:inline-block; padding:7px 11px; border-radius:999px; font-size:.88rem; font-weight:700; margin:3px 0 9px; }
.dash-title { margin-bottom:0; color:var(--navy); }
.dash-subtitle { color:#667488; margin-top:2px; }
.small-muted { font-size:.86rem; color:#687587; }
.st-key-pulso_sticky_analysis_cta { position:fixed !important; left:300px; right:0; bottom:0; z-index:1000; padding:.55rem 1rem .8rem; margin:0; border-top:1px solid var(--line); border-radius:0; background:rgba(248,250,252,.98); box-shadow:0 -8px 24px rgba(15,23,42,.10); backdrop-filter:blur(10px); }
.st-key-pulso_sticky_analysis_cta [data-testid="stFormSubmitButton"] { max-width:24rem; margin-left:4.5rem; }
.st-key-pulso_sticky_analysis_cta [data-testid="stFormSubmitButton"] button { min-height:3.1rem; }
@media (min-width: 641px) and (max-width: 1100px) {
 [data-testid="stHorizontalBlock"] { flex-direction:column !important; gap:1rem !important; }
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { width:100% !important; max-width:100% !important; flex:1 1 100% !important; }
}
@media (max-width: 1100px) {
 .st-key-pulso_sticky_analysis_cta { left:0; right:0; padding:.5rem .75rem .7rem; }
 .st-key-pulso_sticky_analysis_cta [data-testid="stFormSubmitButton"] { max-width:none; margin-left:0; }
}
@media (max-width: 900px) {
 .block-container { padding:1rem .8rem 1.5rem; }
 .login-panel,.st-key-login_right_card { min-height:unset; border-radius:18px; padding:32px 25px; }
 .login-panel .pulso-logo { font-size:2.55rem; }
 .login-panel h1 { margin:35px 0 25px; font-size:2rem; }
 .login-right h2 { margin:16px 0 8px; font-size:1.8rem; }
 .ecg { position:static; margin-top:20px; }
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def _active_settings() -> LLMSettings:
    runtime = st.session_state.get("_llm_runtime_config")
    if isinstance(runtime, dict):
        return get_llm_settings(runtime)
    return get_llm_settings()


def _settings_valid(settings: LLMSettings) -> bool:
    if not settings.ready:
        return False
    try:
        client = LLMHttpClient(settings)
        client.close()
        return True
    except Exception:
        return False


def _redact_ui_value(value: Any, settings: LLMSettings) -> Any:
    if isinstance(value, str):
        return _redact_runtime_labels(value, settings)
    if isinstance(value, list):
        return [_redact_ui_value(item, settings) for item in value]
    if isinstance(value, dict):
        return {
            _redact_runtime_labels(str(key), settings): _redact_ui_value(item, settings)
            for key, item in value.items()
        }
    return value


def _save_llm_settings() -> None:
    api_key = st.session_state.get("pulso_api_key_input", "").strip()
    base_url = st.session_state.get("pulso_base_url_input", "").strip()
    model_name = st.session_state.get("pulso_model_name_input", "").strip()
    if not (api_key and base_url and model_name):
        message = "Preencha os três campos para ativar a configuração nesta sessão."
        if st.session_state.get("_llm_runtime_config"):
            message += " A configuração anterior continua ativa."
        st.session_state["pulso_settings_notice"] = (False, message)
    else:
        settings = LLMSettings(api_key=api_key, base_url=base_url, model_name=model_name)
        if not _settings_valid(settings):
            message = "Configuração inválida. Use um endpoint HTTPS válido, sem credenciais embutidas na URL."
            if st.session_state.get("_llm_runtime_config"):
                message += " A configuração anterior continua ativa."
            st.session_state["pulso_settings_notice"] = (False, message)
        else:
            _invalidate_analysis()
            st.session_state["_llm_runtime_config"] = {
                "api_key": api_key,
                "base_url": base_url,
                "model_name": model_name,
            }
            st.session_state["pulso_settings_notice"] = (True, "Motor configurado somente para esta sessão. Os valores não são exibidos nem gravados em arquivo.")
    for key in ("pulso_api_key_input", "pulso_base_url_input", "pulso_model_name_input"):
        st.session_state[key] = ""


def _handle_login() -> None:
    username = st.session_state.get("pulso_login_user", "")
    password = st.session_state.get("pulso_login_password", "")
    configured_user = os.getenv("PULSO_LOGIN_USERNAME", "")
    encoded_hash = os.getenv("PULSO_LOGIN_PASSWORD_HASH", "")
    if verify_local_login(username, password, configured_user, encoded_hash):
        st.session_state["pulso_authenticated"] = True
        st.session_state["pulso_demo_mode"] = False
        st.session_state["pulso_login_notice"] = None
    else:
        st.session_state["pulso_login_notice"] = "Acesso não validado. Verifique a configuração local ou use a prévia de demonstração."
    st.session_state["pulso_login_password"] = ""


def _logout() -> None:
    _invalidate_analysis()
    for key in (
        "pulso_authenticated", "pulso_demo_mode", "_llm_runtime_config", "analysis_run",
        "case_json_editor", "candidate_case_json", "ocr_preview", "ocr_preview_widget",
        "parse_warnings", "parse_method", "source_summary", "confirm_reviewed", "analysis_error",
        "pulso_login_user", "pulso_login_password", "pulso_login_notice", "pulso_settings_notice",
        "pulso_api_key_input", "pulso_base_url_input", "pulso_model_name_input",
        "record_source_mode", "record_text_input", "record_uploaded_file",
    ):
        st.session_state.pop(key, None)
    for state_key in list(st.session_state.keys()):
        if isinstance(state_key, str) and state_key.startswith("patient_form_"):
            st.session_state.pop(state_key, None)
    st.session_state.pop("candidate_case", None)


def _clear_case() -> None:
    _invalidate_analysis()
    for key in (
        "analysis_run", "case_json_editor", "candidate_case_json", "ocr_preview",
        "ocr_preview_widget", "parse_warnings", "parse_method", "source_summary", "confirm_reviewed",
        "analysis_error", "record_source_mode", "record_text_input", "record_uploaded_file",
    ):
        st.session_state.pop(key, None)
    for state_key in list(st.session_state.keys()):
        if isinstance(state_key, str) and state_key.startswith("patient_form_"):
            st.session_state.pop(state_key, None)
    st.session_state.pop("candidate_case", None)


def _invalidate_analysis() -> None:
    st.session_state.pop("analysis_run", None)
    for key in ("analysis_form_fingerprint", "suggestion_acknowledged", "pulso_accept_confirm", "pulso_accept_notice"):
        st.session_state.pop(key, None)


def _acknowledge_suggestion() -> None:
    run = st.session_state.get("analysis_run")
    current = patient_form_fingerprint(dict(st.session_state))
    if not suggestion_can_be_acknowledged(run) or not st.session_state.get("patient_form_confirm_reviewed") or current != st.session_state.get("analysis_form_fingerprint"):
        st.session_state["pulso_accept_notice"] = "Aceite bloqueado: analise novamente o caso atual e resolva as pendências."
        return
    if not st.session_state.get("pulso_accept_confirm"):
        st.session_state["pulso_accept_notice"] = "Confirme a revisão profissional antes de registrar o aceite."
        return
    st.session_state["suggestion_acknowledged"] = suggestion_fingerprint(run)
    st.session_state.pop("pulso_accept_notice", None)


def _render_login() -> None:
    left, right = st.columns([1.03, 1.12], gap="medium")
    with left:
        st.markdown(
            """
            <div class="login-panel">
              <div class="pulso-logo">Pulso<span>+</span></div>
              <h1>Apoio à decisão<br>clínica com<br>inteligência artificial</h1>
              <div class="login-benefit"><svg viewBox="0 0 24 24"><path d="M12 2 20 5v6c0 5.2-3.4 9-8 11-4.6-2-8-5.8-8-11V5l8-3Z"/><path d="m8.5 12 2.2 2.2 4.8-5"/></svg><span>Segurança por camadas</span></div>
              <div class="login-benefit"><svg viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7M9 16h7"/></svg><span>Diretrizes clínicas estruturadas</span></div>
              <div class="login-benefit"><svg viewBox="0 0 24 24"><path d="M20.8 8.8c0 5.2-8.8 11-8.8 11S3.2 14 3.2 8.8A4.7 4.7 0 0 1 12 6.2a4.7 4.7 0 0 1 8.8 2.6Z"/></svg><span>Revisão profissional sempre</span></div>
              <svg class="ecg" viewBox="0 0 800 80" preserveAspectRatio="none" aria-hidden="true"><path d="M0 43H150c18 0 22-13 40-13s22 13 40 13h93c12 0 12-11 20-11 9 0 10 11 17 11h10l12-65 17 112 14-47h31c17 0 21-13 41-13s24 13 42 13h221" fill="none" stroke="#33dfb1" stroke-width="2.3"/></svg>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        with st.container(key="login_right_card"):
            st.markdown("## Bem-vindo de volta")
            st.markdown("Acesse o Pulso+ e continue apoiando o cuidado na Atenção Primária.")
            with st.form("pulso_login_form"):
                st.text_input("E-mail ou usuário", key="pulso_login_user", placeholder="E-mail ou usuário", label_visibility="collapsed")
                st.text_input("Senha", type="password", key="pulso_login_password", placeholder="Senha", label_visibility="collapsed")
                st.form_submit_button("Entrar", type="primary", use_container_width=True, on_click=_handle_login)
            if st.button("Esqueceu sua senha?", key="pulso_forgot_password"):
                st.info("A recuperação de senha precisa ser configurada pelo administrador deste ambiente.")
            notice = st.session_state.get("pulso_login_notice")
            if notice:
                st.warning(notice)
            st.markdown(
                '<div class="login-footer">Esta prévia não persiste casos no projeto. Use apenas dados simulados ou desidentificados.</div>',
                unsafe_allow_html=True,
            )
        st.write("")
        st.info("Autenticação institucional ainda não configurada? A prévia abaixo não autentica identidade e é somente para testar a interface.")
        if st.button("Abrir prévia de demonstração", key="pulso_demo_login", use_container_width=True):
            st.session_state["pulso_authenticated"] = True
            st.session_state["pulso_demo_mode"] = True
            st.rerun()


def _render_settings() -> None:
    st.title("Configuração segura")
    st.caption("Motor de Análise Clínica Pulso+ · credenciais mascaradas e mantidas somente na sessão atual.")
    settings = _active_settings()
    if _settings_valid(settings):
        origin = "sessão atual" if st.session_state.get("_llm_runtime_config") else "ambiente local"
        st.success(f"Motor configurado via {origin}. Os valores permanecem ocultos.")
    elif settings.ready:
        st.warning("Os campos de configuração existem, mas o endpoint não passou na validação local.")
    else:
        st.info("Configure os três valores abaixo ou use variáveis genéricas no arquivo .env local, ignorado pelo Git.")
    with st.form("pulso_llm_settings_form"):
        st.text_input("Chave de acesso", type="password", key="pulso_api_key_input", placeholder="Cole a chave; ela não será exibida")
        st.text_input("Endpoint do motor", type="password", key="pulso_base_url_input", placeholder="URL base ou endpoint de chat")
        st.text_input("Nome do modelo", type="password", key="pulso_model_name_input", placeholder="Identificador do modelo configurado")
        st.form_submit_button("Ativar nesta sessão", type="primary", use_container_width=True, on_click=_save_llm_settings)
    notice = st.session_state.get("pulso_settings_notice")
    if notice:
        (st.success if notice[0] else st.warning)(notice[1])
    if st.session_state.get("_llm_runtime_config") and st.button("Remover configuração desta sessão", key="pulso_clear_llm"):
        _invalidate_analysis()
        st.session_state.pop("_llm_runtime_config", None)
        st.session_state["pulso_settings_notice"] = (True, "Configuração da sessão removida da memória do aplicativo.")
        st.rerun()
    with st.expander("Privacidade da configuração"):
        st.write("A configuração da tela não é escrita em arquivo nem apresentada após salvar. Ao encerrar a sessão, os valores em memória deixam de estar disponíveis. Não cole segredos em mensagens, casos, observações ou capturas de tela.")


def _format_schema_errors(exc: ValidationError) -> list[str]:
    result = []
    for error in exc.errors(include_input=False):
        location = ".".join(str(item) for item in error.get("loc", ())) or "caso"
        result.append(f"{location}: {error.get('msg', 'valor inválido')}")
    return result


def _choice_from_bool(value: bool | None) -> str:
    if value is True:
        return "Sim"
    if value is False:
        return "Não"
    return "Não informado"


def _bool_from_choice(value: str) -> bool | None:
    if value == "Sim":
        return True
    if value == "Não":
        return False
    return None


def _split_form_items(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[,;\n]+", value) if part.strip()]


def _candidate_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _seed_patient_form(candidate: dict[str, Any]) -> None:
    exams = candidate.get("exames_recentes") or {}
    consultations = candidate.get("consultas") or []
    first = consultations[0] if len(consultations) > 0 else {}
    second = consultations[1] if len(consultations) > 1 else {}
    sex = candidate.get("sexo")
    medicines = candidate.get("medicamentos_em_uso")
    seeds = {
        "patient_form_age": candidate.get("idade"),
        "patient_form_sex": "Feminino" if sex == "F" else "Masculino" if sex == "M" else "Não informado",
        "patient_form_pa1_date": _candidate_date(first.get("data")),
        "patient_form_pas1": first.get("pas"),
        "patient_form_pad1": first.get("pad"),
        "patient_form_pa2_date": _candidate_date(second.get("data")),
        "patient_form_pas2": second.get("pas"),
        "patient_form_pad2": second.get("pad"),
        "patient_form_creatinina": exams.get("creatinina"),
        "patient_form_colesterol_total": exams.get("colesterol_total"),
        "patient_form_hdl": exams.get("hdl"),
        "patient_form_egfr": exams.get("drfg_estimada"),
        "patient_form_imc": exams.get("imc"),
        "patient_form_potassio": exams.get("potassio"),
        "patient_form_hba1c": exams.get("hba1c"),
        "patient_form_troponina": exams.get("troponina"),
        "patient_form_ckmb": exams.get("ckmb"),
        "patient_form_ckmb_limit": exams.get("ckmb_limite_superior"),
        "patient_form_diabetes": _choice_from_bool(candidate.get("diabetes")),
        "patient_form_smoking": _choice_from_bool(candidate.get("tabagismo_atual")),
        "patient_form_antihypertensive": _choice_from_bool(candidate.get("em_uso_anti_hipertensivo")),
        "patient_form_statin": _choice_from_bool(candidate.get("em_uso_estatina")),
        "patient_form_prior_cvd": _choice_from_bool(candidate.get("doenca_cardiovascular_previa")),
        "patient_form_pregnant": _choice_from_bool(candidate.get("gestante")),
        "patient_form_secondary_htn": _choice_from_bool(candidate.get("suspeita_hipertensao_secundaria")),
        "patient_form_comorbidities": ", ".join(candidate.get("comorbidades") or []),
        "patient_form_medicines": ", ".join(item.get("nome", "") for item in medicines or []),
        "patient_form_no_medicines": medicines == [],
        "patient_form_symptoms": ", ".join(candidate.get("sintomas_atuais") or []),
        "patient_form_confirm_reviewed": False,
    }
    for key, value in seeds.items():
        st.session_state[key] = value


def _ensure_patient_form_defaults() -> None:
    for key in (
        "patient_form_age", "patient_form_pa1_date", "patient_form_pas1", "patient_form_pad1",
        "patient_form_pa2_date", "patient_form_pas2", "patient_form_pad2", "patient_form_creatinina",
        "patient_form_colesterol_total", "patient_form_hdl", "patient_form_egfr", "patient_form_imc",
        "patient_form_potassio", "patient_form_hba1c", "patient_form_troponina", "patient_form_ckmb",
        "patient_form_ckmb_limit",
    ):
        st.session_state.setdefault(key, None)
    for key in (
        "patient_form_sex", "patient_form_diabetes", "patient_form_smoking", "patient_form_antihypertensive",
        "patient_form_statin", "patient_form_prior_cvd", "patient_form_pregnant", "patient_form_secondary_htn",
    ):
        st.session_state.setdefault(key, "Não informado")
    for key in ("patient_form_comorbidities", "patient_form_medicines", "patient_form_symptoms"):
        st.session_state.setdefault(key, "")
    st.session_state.setdefault("patient_form_no_medicines", False)
    st.session_state.setdefault("patient_form_confirm_reviewed", False)


def _render_case_input() -> None:
    fingerprint = st.session_state.get("analysis_form_fingerprint")
    if fingerprint and fingerprint != patient_form_fingerprint(dict(st.session_state)):
        _invalidate_analysis()
    st.subheader("Dados do paciente")
    st.caption("Cole um texto desidentificado ou envie PDF/imagem. O OCR e a extração ocorrem localmente.")
    with st.container(border=True):
        source_mode = st.radio("Origem", ["Colar texto", "PDF / imagem"], horizontal=True, key="record_source_mode")
        pasted_text = ""
        uploaded = None
        extract_submitted = False
        if source_mode == "Colar texto":
            with st.form("pulso_record_form", clear_on_submit=True):
                pasted_text = st.text_area("Texto do prontuário", height=150, placeholder="Remova nome, documento, telefone e outros identificadores antes de colar.", key="record_text_input")
                extract_submitted = st.form_submit_button("Extrair campos para revisão", use_container_width=True)
        else:
            uploaded = st.file_uploader("Enviar documento", type=["pdf", "png", "jpg", "jpeg", "tif", "tiff", "bmp"], accept_multiple_files=False, key="record_uploaded_file")
            extract_submitted = st.button("Extrair campos para revisão", use_container_width=True, key="pulso_extract_document")
    if extract_submitted:
        try:
            if source_mode == "Colar texto":
                source_text = pasted_text.strip()
                method = "texto colado; processamento local"
                if not source_text:
                    raise LocalExtractionError("Cole um texto ou envie um arquivo antes de extrair.")
            else:
                if uploaded is None:
                    raise LocalExtractionError("Selecione um arquivo antes de extrair.")
                extracted = extract_document_text(uploaded.name, uploaded.getvalue())
                source_text, method = extracted.text, extracted.method
            candidate, warnings = parse_clinical_text(source_text)
            st.session_state["candidate_case"] = candidate
            _seed_patient_form(candidate)
            st.session_state["ocr_preview"] = source_text
            st.session_state["ocr_preview_widget"] = source_text
            st.session_state["parse_method"] = method
            st.session_state["parse_warnings"] = warnings
            st.session_state["source_summary"] = f"Extração concluída: {method}. Revise cada campo; valores ausentes permanecem em branco."
            st.session_state.pop("analysis_error", None)
            _invalidate_analysis()
        except LocalExtractionError as exc:
            st.session_state["source_summary"] = str(exc)
            st.session_state["ocr_preview"] = ""
            st.session_state["parse_warnings"] = []
            _invalidate_analysis()
        except Exception:
            st.session_state["source_summary"] = "Não foi possível processar o conteúdo. Revise o formato e tente novamente."
            st.session_state["ocr_preview"] = ""
            st.session_state["parse_warnings"] = []
            _invalidate_analysis()

    summary = st.session_state.get("source_summary")
    if summary:
        st.info(summary)
    for warning in st.session_state.get("parse_warnings", []):
        st.warning(warning)
    if st.session_state.get("ocr_preview"):
        with st.expander("Texto reconhecido — permanece somente nesta sessão"):
            st.text_area("Prévia local", key="ocr_preview_widget", height=120, disabled=True, label_visibility="collapsed")

    _ensure_patient_form_defaults()
    choices = ["Não informado", "Sim", "Não"]
    with st.container(key="pulso_patient_form"):
        st.markdown("#### Identificação clínica")
        identity_left, identity_right = st.columns(2)
        age = identity_left.number_input("Idade (anos)", min_value=0, max_value=120, step=1, value=None, key="patient_form_age")
        sex_choice = identity_right.selectbox("Sexo", ["Não informado", "Feminino", "Masculino"], key="patient_form_sex")

        st.markdown("#### Pressão arterial")
        st.caption("Registre até duas aferições. Datas/valores não são inferidos quando ausentes.")
        consultations = []
        for number in (1, 2):
            st.caption(f"Aferição {number}")
            reading_date = st.date_input("Data", value=None, key=f"patient_form_pa{number}_date", format="DD/MM/YYYY")
            pas_col, pad_col = st.columns(2)
            pas = pas_col.number_input("PAS (mmHg)", value=None, step=1, key=f"patient_form_pas{number}")
            pad = pad_col.number_input("PAD (mmHg)", value=None, step=1, key=f"patient_form_pad{number}")
            if pas is not None or pad is not None:
                consultation: dict[str, Any] = {"pas": pas, "pad": pad}
                if reading_date is not None:
                    consultation["data"] = reading_date
                consultations.append(consultation)

        st.markdown("#### Exames e medidas")
        lab_1, lab_2 = st.columns(2)
        creatinina = lab_1.number_input("Creatinina (mg/dL)", value=None, step=0.1, format="%.2f", key="patient_form_creatinina")
        colesterol_total = lab_2.number_input("Colesterol total (mg/dL)", value=None, step=1.0, format="%.0f", key="patient_form_colesterol_total")
        lab_3, lab_4 = st.columns(2)
        hdl = lab_3.number_input("HDL (mg/dL)", value=None, step=1.0, format="%.0f", key="patient_form_hdl")
        egfr = lab_4.number_input("eGFR / TFGe (mL/min)", value=None, step=1.0, format="%.1f", key="patient_form_egfr")
        lab_5, lab_6 = st.columns(2)
        imc = lab_5.number_input("IMC (kg/m²)", value=None, step=0.1, format="%.1f", key="patient_form_imc")
        potassio = lab_6.number_input("Potássio (mEq/L)", value=None, step=0.1, format="%.2f", key="patient_form_potassio")
        lab_7, lab_8 = st.columns(2)
        hba1c = lab_7.number_input("HbA1c (%)", value=None, step=0.1, format="%.1f", key="patient_form_hba1c")
        troponina = lab_8.number_input("Troponina", value=None, step=0.01, format="%.3f", key="patient_form_troponina")
        lab_9, lab_10 = st.columns(2)
        ckmb = lab_9.number_input("CK-MB", value=None, step=0.1, format="%.2f", key="patient_form_ckmb")
        ckmb_limit = lab_10.number_input("Referência superior CK-MB", value=None, step=0.1, format="%.2f", key="patient_form_ckmb_limit")

        st.markdown("#### Fatores clínicos")
        factor_1, factor_2 = st.columns(2)
        diabetes_choice = factor_1.selectbox("Diabetes", choices, key="patient_form_diabetes")
        smoking_choice = factor_2.selectbox("Tabagismo atual", choices, key="patient_form_smoking")
        factor_3, factor_4 = st.columns(2)
        antihypertensive_choice = factor_3.selectbox("Anti-hipertensivo em uso", choices, key="patient_form_antihypertensive")
        statin_choice = factor_4.selectbox("Estatina em uso", choices, key="patient_form_statin")
        factor_5, factor_6 = st.columns(2)
        prior_cvd_choice = factor_5.selectbox("DCV prévia", choices, key="patient_form_prior_cvd")
        pregnant_choice = factor_6.selectbox("Gestação", choices, key="patient_form_pregnant")
        secondary_htn_choice = st.selectbox("Suspeita de hipertensão secundária", choices, key="patient_form_secondary_htn")

        st.markdown("#### Histórico e tratamento")
        comorbidities_text = st.text_input("Comorbidades (separe por vírgula)", key="patient_form_comorbidities")
        medicines_text = st.text_input("Medicamentos em uso (separe por vírgula)", key="patient_form_medicines")
        no_medicines = st.checkbox("Sem medicamentos em uso", key="patient_form_no_medicines")
        symptoms_text = st.text_input("Sintomas atuais (separe por vírgula)", key="patient_form_symptoms")
        consent = st.checkbox("Confirmo que desidentifiquei o caso e revisei os campos.", key="patient_form_confirm_reviewed")
        st.caption("Texto bruto e OCR permanecem locais; somente o formulário estruturado, após confirmação, é enviado ao motor.")
        with st.container(key="pulso_sticky_analysis_cta"):
            analyze_submitted = st.button("Validar e analisar", type="primary", use_container_width=True, key="pulso_submit_case")

    if analyze_submitted:
        _invalidate_analysis()
        st.session_state.pop("analysis_error", None)
        if not consent:
            st.warning("Confirme a desidentificação e a revisão dos campos antes de analisar.")
            return
        if no_medicines and medicines_text.strip():
            st.error("Remova os medicamentos ou desmarque ‘Sem medicamentos em uso’.")
            return
        medicines = [] if no_medicines else ([{"nome": name} for name in _split_form_items(medicines_text)] or None)
        lab_values = {
            "creatinina": creatinina,
            "colesterol_total": colesterol_total,
            "hdl": hdl,
            "drfg_estimada": egfr,
            "imc": imc,
            "potassio": potassio,
            "hba1c": hba1c,
            "troponina": troponina,
            "ckmb": ckmb,
            "ckmb_limite_superior": ckmb_limit,
        }
        case_payload = {
            "caso_id": "CASO-LOCAL",
            "idade": age,
            "sexo": "F" if sex_choice == "Feminino" else "M" if sex_choice == "Masculino" else None,
            "consultas": consultations,
            "medicamentos_em_uso": medicines,
            "comorbidades": _split_form_items(comorbidities_text),
            "exames_recentes": {key: value for key, value in lab_values.items() if value is not None},
            "sintomas_atuais": _split_form_items(symptoms_text) or None,
            "diabetes": _bool_from_choice(diabetes_choice),
            "tabagismo_atual": _bool_from_choice(smoking_choice),
            "em_uso_anti_hipertensivo": _bool_from_choice(antihypertensive_choice),
            "em_uso_estatina": _bool_from_choice(statin_choice),
            "doenca_cardiovascular_previa": _bool_from_choice(prior_cvd_choice),
            "gestante": _bool_from_choice(pregnant_choice),
            "suspeita_hipertensao_secundaria": _bool_from_choice(secondary_htn_choice),
        }
        try:
            case = PacienteHAS.model_validate(case_payload)
        except ValidationError as exc:
            st.error("Os campos não passaram pela validação local. Revise os valores informados:")
            for line in _format_schema_errors(exc):
                st.write(f"- {line}")
            return
        settings = _active_settings()
        agent = None
        try:
            agent = ClinicalAgent(
                api_key=settings.api_key,
                base_url=settings.base_url,
                model_name=settings.model_name,
            )
            st.session_state["analysis_run"] = agent.analyze(case)
            st.session_state["analysis_form_fingerprint"] = patient_form_fingerprint(dict(st.session_state))
        except Exception:
            st.session_state["analysis_error"] = "A análise foi interrompida por uma falha segura. Nenhum detalhe técnico ou dado do caso foi registrado na tela."
            st.session_state.pop("analysis_run", None)
        finally:
            if agent is not None and isinstance(agent.client, LLMHttpClient):
                agent.client.close()


def _status_for_run(run: Any) -> tuple[str, str, str]:
    output = run.saida
    if any(item.resultado.get("alerta_vermelho") for item in run.ferramentas):
        return "red", "Alerta vermelho", "Encaminhamento urgente"
    if not suggestion_can_be_acknowledged(run):
        return "amber", "Revisão humana necessária", "Sugestão pendente de avaliação"
    return "green", "Análise concluída", "Sugestão para revisão profissional"


def _conduct_label(value: str) -> str:
    labels = {
        "manter": "Manter sob acompanhamento profissional",
        "ajustar_dose": "Revisar possível ajuste",
        "adicionar_segunda_classe": "Avaliar estratégia terapêutica",
        "trocar_classe": "Revisar estratégia terapêutica",
        "encaminhar_especialista": "Encaminhar para avaliação urgente",
        "revisao_humana_necessaria": "Revisão humana necessária",
    }
    return labels.get(value, "Revisão humana necessária")


def _render_dashboard() -> None:
    if st.session_state.get("pulso_demo_mode"):
        st.warning("Prévia de demonstração — sem autenticação institucional. Não use dados identificáveis nem casos reais.")
    else:
        st.info("Sessão local. O aplicativo não grava casos no projeto.")
    st.markdown('<h1 class="dash-title">Motor de Análise Clínica Pulso+</h1>', unsafe_allow_html=True)
    st.markdown('<div class="dash-subtitle">Apoio à decisão clínica · Hipertensão · revisão profissional obrigatória</div>', unsafe_allow_html=True)
    st.write("")
    error = st.session_state.pop("analysis_error", None)
    if error:
        st.error(error)

    left, center, right = st.columns([1.08, 1.0, 1.0], gap="medium")
    with left:
        with st.container(border=True):
            _render_case_input()
            st.button("Limpar dados desta sessão", key="pulso_clear_case", use_container_width=True, on_click=_clear_case)
    run = st.session_state.get("analysis_run")
    if run is not None:
        settings = _active_settings()
        for tool_trace in run.ferramentas:
            tool_trace.nome = _redact_runtime_labels(tool_trace.nome, settings)
            tool_trace.argumentos = _redact_ui_value(tool_trace.argumentos, settings)
            tool_trace.resultado = _redact_ui_value(tool_trace.resultado, settings)
    with center:
        with st.container(border=True):
            st.subheader("Raciocínio da IA")
            st.caption("Trilha auditável de ferramentas e resultados; não exibe raciocínio interno privado.")
            if run is None:
                st.info("Após validar os dados, as etapas determinísticas aparecerão aqui.")
            else:
                tone, title, _ = _status_for_run(run)
                st.markdown(f'<span class="status-chip status-{tone}">{title}</span>', unsafe_allow_html=True)
                if run.fluxo_abortado:
                    st.warning("Fluxo automático interrompido por uma regra de segurança.")
                if not run.ferramentas:
                    st.info("Nenhuma ferramenta executada.")
                for index, item in enumerate(run.ferramentas, start=1):
                    status = "executada" if item.executada else "bloqueada"
                    with st.expander(f"{index}. {item.nome} · {status}", expanded=index == 1):
                        st.caption(f"Origem: {item.origem}")
                        st.markdown("**Argumentos**")
                        st.json(item.argumentos, expanded=False)
                        st.markdown("**Resultado**")
                        st.json(item.resultado, expanded=False)
    with right:
        with st.container(border=True, key="pulso_suggestion_card"):
            st.subheader("Conduta sugerida")
            st.caption("Saída do motor para revisão profissional; não é prescrição.")
            if run is None:
                st.info("A conduta aparecerá após a análise do caso.")
            else:
                output = run.saida
                tone, title, subtitle = _status_for_run(run)
                st.markdown(f'<span class="status-chip status-{tone}">{title}</span>', unsafe_allow_html=True)
                st.markdown(f"### {_conduct_label(output.conduta_sugerida)}")
                st.write(output.detalhe_conduta)
                st.markdown("**Justificativa**")
                st.write(output.justificativa)
                st.markdown("**Risco cardiovascular**")
                st.write(output.risco_cardiovascular.replace("_", " ").capitalize())
                risk_trace = next((item for item in run.ferramentas if item.nome == "estratificar_risco_cardio" and item.origem == "preflight"), None)
                if risk_trace and risk_trace.resultado.get("risco_percentual_10_anos") is not None:
                    st.caption(f"PREVENT-CVD: {risk_trace.resultado['risco_percentual_10_anos']:.2f}% em 10 anos.")
                st.caption("Modelo derivado nos EUA, sem calibração brasileira; estimativa de apoio, não certeza individual.")
                st.markdown("**Confiança**")
                st.write(output.nivel_confianca.capitalize())
                if output.necessita_revisao_humana:
                    st.warning("Revisão humana necessária antes de qualquer decisão.")
                if output.dados_faltantes:
                    st.markdown("**Dados faltantes**")
                    for item in output.dados_faltantes:
                        st.write(f"- {item}")
                if output.medicamentos_verificados:
                    st.markdown("**Checagem de medicamentos do caso**")
                    for medication in output.medicamentos_verificados:
                        state = "Na lista verificada" if medication.disponivel_sus else "Não confirmado na lista"
                        if medication.contraindicacao:
                            state += " · possível contraindicação"
                        st.write(f"- {medication.nome}: {state}")
                st.caption(subtitle)
                can_acknowledge = suggestion_can_be_acknowledged(run)
                if can_acknowledge:
                    st.success("Conduta recomendada para avaliação profissional — não é prescrição.")
                    st.checkbox("Revisei a sugestão como profissional responsável.", key="pulso_accept_confirm")
                st.caption("Registra somente a revisão nesta sessão; não aceita prescrição, dose ou execução de conduta.")
                st.button(
                    "Aceitar Sugestão", type="primary", use_container_width=True,
                    key="pulso_accept_suggestion", disabled=not can_acknowledge,
                    on_click=_acknowledge_suggestion,
                )
                notice = st.session_state.get("pulso_accept_notice")
                if notice:
                    st.warning(notice)
                if st.session_state.get("suggestion_acknowledged") == suggestion_fingerprint(run):
                    st.success("Aceite registrado somente nesta sessão. Nenhuma prescrição, ajuste de dose ou gravação no prontuário foi executado.")
                st.caption("Aceitar registra a revisão apenas em memória; qualquer edição exige nova análise.")


def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown('<div class="pulso-logo">Pulso<span>+</span></div>', unsafe_allow_html=True)
        st.caption("Motor de Análise Clínica")
        page = st.radio("Navegação", ["Análise clínica", "Configuração", "Ajuda"], label_visibility="collapsed")
        st.divider()
        settings = _active_settings()
        st.caption("Motor configurado" if _settings_valid(settings) else "Motor ainda não configurado")
        st.button("Sair e limpar sessão", use_container_width=True, on_click=_logout)
        return page


def main() -> None:
    if not st.session_state.get("pulso_authenticated"):
        _render_login()
        st.stop()
    page = _render_sidebar()
    if page == "Configuração":
        _render_settings()
    elif page == "Ajuda":
        st.title("Ajuda")
        st.write("Revise os campos extraídos antes da análise. O OCR pode errar valores; a decisão final permanece com o profissional.")
        st.write("O app não salva prontuários, não registra aceite de conduta e não integra com sistemas clínicos.")
        st.write("A autenticação de demonstração é apenas visual. Configure um acesso local com hash PBKDF2 antes de qualquer teste institucional.")
    else:
        _render_dashboard()


if __name__ == "__main__":
    main()
