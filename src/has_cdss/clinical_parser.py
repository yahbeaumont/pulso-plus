from __future__ import annotations

import io
import re
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_IMAGE_PIXELS = 25_000_000
MAX_TEXT_CHARS = 50_000
_ALLOWED_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
_EXTRACTION_SLOT = threading.BoundedSemaphore(1)


class LocalExtractionError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    method: str


def _ocr_image(image: Any) -> str:
    if not shutil.which("tesseract"):
        raise LocalExtractionError("OCR local não está instalado neste ambiente.")
    try:
        import pytesseract
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image).convert("RGB")
        languages = set(pytesseract.get_languages(config=""))
        language = "por" if "por" in languages else "eng"
        return pytesseract.image_to_string(image, lang=language, config="--psm 6", timeout=30)
    except LocalExtractionError:
        raise
    except Exception:
        raise LocalExtractionError("Não foi possível extrair texto localmente do arquivo.") from None


def extract_document_text(filename: str, data: bytes) -> ExtractionResult:
    if not _EXTRACTION_SLOT.acquire(blocking=False):
        raise LocalExtractionError("Extração local ocupada. Aguarde a conclusão da extração em curso e tente novamente.")
    try:
        return _extract_document_text(filename, data)
    finally:
        _EXTRACTION_SLOT.release()


def _extract_document_text(filename: str, data: bytes) -> ExtractionResult:
    """Extrai texto em memória. Não salva o arquivo nem envia imagem/PDF para serviços externos."""
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise LocalExtractionError("Arquivo vazio ou acima do limite de 10 MB.")
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data), strict=True)
            if len(reader.pages) > MAX_PDF_PAGES:
                raise LocalExtractionError("PDF acima do limite de 10 páginas.")
            page_count = len(reader.pages)
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if len(text) >= 20:
                return ExtractionResult(text=text[:MAX_TEXT_CHARS], method="texto do PDF extraído localmente")
        except LocalExtractionError:
            raise
        except Exception:
            raise LocalExtractionError("Não foi possível ler o PDF; use um arquivo válido e sem senha.") from None
        try:
            from pdf2image import convert_from_bytes

            recognized = []
            for number in range(1, page_count + 1):
                pages = convert_from_bytes(data, dpi=220, size=2200, first_page=number, last_page=number, thread_count=1, timeout=45)
                try:
                    recognized.extend(_ocr_image(page) for page in pages)
                finally:
                    for page in pages:
                        page.close()
            text = "\n".join(recognized).strip()
            if not text:
                raise LocalExtractionError("Nenhum texto legível encontrado no PDF.")
            return ExtractionResult(text=text[:MAX_TEXT_CHARS], method="OCR local de PDF")
        except LocalExtractionError:
            raise
        except Exception:
            raise LocalExtractionError("Falha no OCR local do PDF; tente uma imagem mais nítida ou PDF pesquisável.") from None

    if extension in _ALLOWED_IMAGES:
        try:
            from PIL import Image

            image = Image.open(io.BytesIO(data))
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise LocalExtractionError("Imagem acima do limite de resolução permitido.")
            text = _ocr_image(image).strip()
            if not text:
                raise LocalExtractionError("Nenhum texto legível encontrado na imagem.")
            return ExtractionResult(text=text[:MAX_TEXT_CHARS], method="OCR local de imagem")
        except LocalExtractionError:
            raise
        except Exception:
            raise LocalExtractionError("Não foi possível ler a imagem enviada.") from None

    raise LocalExtractionError("Formato não suportado. Use PDF, PNG, JPG ou TIFF.")


def _number(text: str) -> float:
    return float(text.replace(" ", "").replace(".", "").replace(",", ".") if "," in text else text)


def _first(pattern: str, text: str, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def _explicit_yes_no(text: str, labels: str) -> bool | None:
    value = _first(rf"(?:{labels})\s*[:=]\s*(sim|s|não|nao|n)", text)
    if value is None:
        return None
    return value.casefold() in {"sim", "s"}


def _date(text: str) -> str | None:
    raw = _first(r"(?:data\s*(?:da\s*)?(?:aferi[cç][aã]o|consulta|registro)?)\s*[:=]\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})", text)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def parse_clinical_text(text: str) -> tuple[dict[str, Any], list[str]]:
    """Gera candidatos estruturados somente de rótulos explícitos; não faz diagnóstico nem imputação."""
    text = text[:MAX_TEXT_CHARS]
    candidate: dict[str, Any] = {
        "caso_id": "CASO-LOCAL",
        "consultas": [],
        "medicamentos_em_uso": None,
        "comorbidades": [],
        "exames_recentes": {},
        "sintomas_atuais": None,
    }
    warnings = ["Extração candidata: confira/corrija cada campo antes da análise; texto bruto não é enviado ao motor."]

    age = _first(r"(?:idade)\s*[:=]\s*(\d{1,3})\s*(?:anos?)?\b", text)
    if age:
        candidate["idade"] = int(age)

    sex = _first(r"(?:sexo|g[eê]nero)\s*[:=]\s*(feminino|masculino|mulher|homem|f|m)\b", text)
    if sex:
        candidate["sexo"] = "F" if sex.casefold() in {"feminino", "mulher", "f"} else "M"

    pairs = re.findall(r"\b(?:PA|press[aã]o\s+arterial)\s*[:=]?\s*(\d{2,3})\s*(?:/|x|×)\s*(\d{2,3})\b", text, re.IGNORECASE)
    pas_only = _first(r"\bPAS\s*[:=]\s*(\d{2,3})\b", text)
    pad_only = _first(r"\bPAD\s*[:=]\s*(\d{2,3})\b", text)
    if pairs:
        pas, pad = pairs[-1]
        consulta: dict[str, Any] = {"pas": int(pas), "pad": int(pad)}
        if len(pairs) > 1:
            warnings.append("Mais de uma PA foi encontrada; foi carregada somente a última. Confirme datas e ocasiões manualmente.")
    elif pas_only or pad_only:
        consulta = {"pas": int(pas_only) if pas_only else None, "pad": int(pad_only) if pad_only else None}
    else:
        consulta = {}
    if consulta:
        recorded_date = _date(text)
        if recorded_date:
            consulta["data"] = recorded_date
        candidate["consultas"].append(consulta)

    exam_patterns = {
        "colesterol_total": r"(?:colesterol\s+total)\s*[:=]\s*(\d{2,3}(?:[.,]\d+)?)",
        "hdl": r"\bHDL(?:-c)?\s*[:=]\s*(\d{1,3}(?:[.,]\d+)?)",
        "drfg_estimada": r"(?:eGFR|TFGe|filtra[cç][aã]o\s+glomerular\s+estimada)\s*[:=<>≥]*\s*(\d{1,3}(?:[.,]\d+)?)",
        "imc": r"\bIMC\s*[:=]\s*(\d{1,2}(?:[.,]\d+)?)",
        "potassio": r"(?:pot[aá]ssio|\bK\+)\s*[:=]\s*(\d(?:[.,]\d+)?)",
        "creatinina": r"\bcreatinina\s*[:=]\s*(\d+(?:[.,]\d+)?)",
        "hba1c": r"(?:HbA1c|hemoglobina\s+glicada)\s*[:=]\s*(\d+(?:[.,]\d+)?)",
        "troponina": r"\btroponina(?:\s+[IT])?\s*[:=<>]*\s*(\d+(?:[.,]\d+)?)",
        "ckmb": r"\bCK\s*[- ]?\s*MB\s*[:=<>]*\s*(\d+(?:[.,]\d+)?)",
        "ckmb_limite_superior": r"(?:limite\s+superior\s+(?:do\s+)?CK\s*[- ]?\s*MB|refer[eê]ncia\s+(?:do\s+)?CK\s*[- ]?\s*MB)\s*[:=]\s*(\d+(?:[.,]\d+)?)",
    }
    for field, pattern in exam_patterns.items():
        raw = _first(pattern, text)
        if raw is not None:
            candidate["exames_recentes"][field] = _number(raw)

    diabetes = _explicit_yes_no(text, r"(?:diabetes|DM)")
    if diabetes is None and re.search(r"\bdiabetes\s+(?:mellitus\s+)?tipo\s+[12]\b", text, re.IGNORECASE):
        diabetes = True
    if diabetes is None and re.search(r"\bsem\s+diabetes\b", text, re.IGNORECASE):
        diabetes = False
    if diabetes is not None:
        candidate["diabetes"] = diabetes

    for field, label in (
        ("tabagismo_atual", r"(?:tabagismo\s+atual|fumante\s+atual)"),
        ("em_uso_anti_hipertensivo", r"(?:anti[- ]hipertensivo\s+em\s+uso|em\s+uso\s+de\s+anti[- ]hipertensivo)"),
        ("em_uso_estatina", r"(?:estatina\s+em\s+uso|em\s+uso\s+de\s+estatina)"),
        ("doenca_cardiovascular_previa", r"(?:DCV\s+pr[eé]via|doen[cç]a\s+cardiovascular\s+pr[eé]via)"),
        ("gestante", r"(?:gestante|gesta[cç][aã]o)"),
        ("suspeita_hipertensao_secundaria", r"(?:suspeita\s+de\s+hipertens[aã]o\s+secund[aá]ria)"),
    ):
        value = _explicit_yes_no(text, label)
        if value is not None:
            candidate[field] = value

    medicines_line = _first(r"(?:medicamentos?\s+em\s+uso)\s*[:=]\s*([^\n\r]+)", text)
    if medicines_line:
        if re.fullmatch(r"\s*(?:nenhum|nenhuma|n[aã]o usa|sem medicamentos?)\s*[.!]?\s*", medicines_line, re.IGNORECASE):
            candidate["medicamentos_em_uso"] = []
        else:
            names = [item.strip(" .;-") for item in re.split(r"[,;]", medicines_line) if item.strip(" .;-")]
            candidate["medicamentos_em_uso"] = [{"nome": name} for name in names if name]

    symptoms_line = _first(r"(?:sintomas?\s+atuais)\s*[:=]\s*([^\n\r]+)", text)
    if symptoms_line:
        candidate["sintomas_atuais"] = [item.strip(" .;-") for item in re.split(r"[,;]", symptoms_line) if item.strip(" .;-")]

    return candidate, warnings
