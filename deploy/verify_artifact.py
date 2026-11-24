from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    try:
        manifest = json.loads((ROOT / "artifact-manifest.json").read_text(encoding="utf-8"))
        files = manifest["sha256"]
        if not files:
            raise ValueError
        for relative, expected in files.items():
            path = (ROOT / relative).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        for required in ["pulso_patient_form", "patient_form_hdl", "patient_form_egfr", "pulso_sticky_analysis_cta"]:
            if required not in app:
                raise ValueError
        if (ROOT / ".env").exists():
            raise ValueError
    except Exception:
        raise SystemExit("Artefato de publicação inválido; inicialização interrompida.") from None
    print("Artefato Pulso+ íntegro; formulário e guardrails disponíveis.")


if __name__ == "__main__":
    main()
