from __future__ import annotations

import os
from playwright.sync_api import sync_playwright

url = os.getenv("PULSO_TEST_URL", "http://127.0.0.1:3000")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.get_by_role("button", name="Abrir prévia de demonstração").click()
    page.get_by_label("Idade (anos)").wait_for(timeout=30000)
    page.get_by_text("Motor ainda não configurado", exact=True).wait_for(timeout=20000)
    page.get_by_text("Configuração", exact=True).click()
    page.get_by_label("Chave de acesso").wait_for(timeout=20000)
    page.get_by_label("Chave de acesso").fill("synthetic-session-key")
    page.get_by_label("Endpoint do motor").fill("https://example.com/v1")
    page.get_by_label("Nome do modelo").fill("synthetic-model")
    page.get_by_role("button", name="Ativar nesta sessão").click()
    page.get_by_text("Motor configurado somente para esta sessão.", exact=False).wait_for(timeout=20000)
    assert "synthetic-session-key" not in page.locator("body").inner_text()
    assert page.get_by_label("Chave de acesso").input_value() == ""
    other = browser.new_page()
    other.goto(url, wait_until="domcontentloaded", timeout=60000)
    other.get_by_role("button", name="Abrir prévia de demonstração").click()
    other.get_by_text("Motor ainda não configurado", exact=True).wait_for(timeout=20000)
    print("two_visitors_isolated=yes")
    page.get_by_text("Análise clínica", exact=True).click()
    page.get_by_label("Texto do prontuário", exact=True).fill("Idade: 58 anos\nSexo: Feminino\nPA: 152/96\nTroponina 2.5")
    page.get_by_role("button", name="Extrair campos para revisão").click()
    page.get_by_text("Extração concluída:", exact=False).wait_for(timeout=20000)
    consent = page.get_by_label("Confirmo que desidentifiquei o caso e revisei os campos.")
    consent.focus()
    consent.press("Space")
    assert consent.is_checked()
    page.get_by_role("button", name="Validar e analisar").click()
    page.get_by_text("Alerta vermelho", exact=True).first.wait_for(timeout=20000)
    assert page.get_by_text("Revisão humana necessária antes de qualquer decisão.", exact=True).is_visible()
    print("red_flag_production_entrypoint=passed")
    print("page_errors=", len(errors))
    assert not errors
    page.close()
    other.close()
    browser.close()
