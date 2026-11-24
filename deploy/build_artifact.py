from __future__ import annotations

import compileall
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    files = [ROOT / name for name in ("app.py", "requirements.lock.txt", "THIRD_PARTY_NOTICES.md")]
    for directory in ("src", "prompts", "static", ".streamlit", "deploy", "public"):
        files.extend(path for path in (ROOT / directory).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    manifest = {
        "version": 1,
        "sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
    }
    (ROOT / "artifact-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in [ROOT / "app.py", ROOT / "src", ROOT / "deploy"]:
        ok = compileall.compile_dir(path, quiet=1) if path.is_dir() else compileall.compile_file(path, quiet=1)
        if not ok:
            raise SystemExit("Compilação do runtime interrompida.")
    if (ROOT / ".env").exists():
        raise SystemExit("Arquivo privado não permitido no artefato de publicação.")
    print(f"Build Python concluído; manifesto com {len(files)} arquivos de runtime.")


if __name__ == "__main__":
    main()
