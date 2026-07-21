"""Form 16 extraction (PyMuPDF regex + Gemini vision, multi-file consolidation)
plus PDF page rendering and term-locating for the CA validation desk."""
import os
import re
import json
import uuid
import tempfile
import logging

import fitz  # PyMuPDF
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage, FileContentWithMimeType
except ImportError:  # Local deterministic parsing remains available without an LLM provider.
    LlmChat = UserMessage = FileContentWithMimeType = None

logger = logging.getLogger(__name__)
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY")

EXTRACTION_PROMPT = """You are a precise Indian tax document extraction assistant. Extract candidate values from this single document only. Never decide which value is final, never combine different employers/accounts, and never infer missing amounts. Return ONLY valid minified JSON with these keys (0 for missing numbers, "" for missing text):
{"document_kind":"form_16|broker_pl|bank_statement|other","employer_name":"","employer_tan":"","employer_pan":"","employee_name":"","employee_pan":"","assessment_year":"","gross_salary":0,"section_10_exemptions":0,"professional_tax":0,"deductions_80c":0,"deductions_80d":0,"tds_deducted":0,"stcg_equity":0,"ltcg_equity":0,"confidence":0.0}
All monetary values are plain numbers (no commas/symbols). confidence is 0-1. Return JSON only, no markdown fences."""

NUMERIC = ["gross_salary", "section_10_exemptions", "professional_tax", "deductions_80c",
           "deductions_80d", "tds_deducted", "stcg_equity", "ltcg_equity"]


def extract_text_local(pdf_bytes: bytes) -> str:
    text = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text.append(page.get_text("text"))
        doc.close()
    except Exception as e:
        logger.warning(f"local text extraction failed: {e}")
    return "\n".join(text)


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "").strip() or 0)
    except Exception:
        return 0.0


def regex_extract(text: str) -> dict:
    flat = " ".join(text.split())

    def m(pattern, default=""):
        r = re.search(pattern, flat, re.IGNORECASE)
        return r.group(1).strip() if r else default

    def n(pattern):
        return _num(m(pattern, "0"))

    data = {
        "document_kind": "form_16" if re.search(r"form\s*no\.?\s*16|section\s*203", flat, re.I) else "other",
        "employer_name": m(r"(?:Name (?:and address )?of the Employer|Employer)\s*:?\s*([A-Za-z0-9 &.,'\-]{3,60}?)(?:\s+TAN|\s+PAN|$)"),
        "employer_tan": m(r"(?:TAN of the Deductor|Employer TAN|TAN)\s*:?\s*([A-Z]{4}[0-9]{5}[A-Z])"),
        "employer_pan": m(r"(?:PAN of the Deductor|Employer PAN)\s*:?\s*([A-Z]{5}[0-9]{4}[A-Z])"),
        "employee_name": m(r"(?:Name of the Employee|Employee)\s*:?\s*([A-Za-z .]{3,50}?)(?:\s+PAN|$)"),
        "employee_pan": m(r"(?:PAN of the Employee|Employee PAN)\s*:?\s*([A-Z]{5}[0-9]{4}[A-Z])"),
        "assessment_year": m(r"Assessment Year\s*:?\s*([0-9]{4}\s*-\s*[0-9]{2,4})"),
        "gross_salary": n(r"Gross Salary(?:.*?17\(1\))?.*?(?:Rs\.?\s*)?([\d,]{4,})"),
        "section_10_exemptions": n(r"(?:exemption|allowances)\s+under\s+section\s+10.*?(?:Rs\.?\s*)?([\d,]{3,})"),
        "professional_tax": n(r"Professional\s*Tax.*?(?:Rs\.?\s*)?([\d,]{2,})"),
        "deductions_80c": n(r"80C.*?(?:Rs\.?\s*)?([\d,]{3,})"),
        "deductions_80d": n(r"80D.*?(?:Rs\.?\s*)?([\d,]{3,})"),
        "tds_deducted": n(r"(?:Total\s+tax\s+deducted\s+at\s+source|TDS).*?(?:Rs\.?\s*)?([\d,]{3,})"),
        "stcg_equity": n(r"(?:Short[ -]?Term|STCG).*?(?:Rs\.?\s*)?([\d,]{3,})"),
        "ltcg_equity": n(r"(?:Long[ -]?Term|LTCG).*?(?:Rs\.?\s*)?([\d,]{3,})"),
    }
    filled = sum(1 for k in ["gross_salary", "section_10_exemptions", "deductions_80c", "tds_deducted"] if data.get(k))
    data["confidence"] = round(min(0.6 + filled * 0.1, 0.95), 2)
    data["source"] = "local_regex"
    return data


def _merge_regex(base: dict, new: dict) -> dict:
    if not base:
        return new
    for k in NUMERIC:
        if not base.get(k) and new.get(k):
            base[k] = new[k]
    for k in ("employer_name", "employer_tan", "employer_pan", "employee_name",
              "employee_pan", "assessment_year"):
        if not base.get(k) and new.get(k):
            base[k] = new[k]
    if new.get("document_kind") == "form_16":
        base["document_kind"] = "form_16"
    return base


async def _gemini_extract(file_contents) -> dict:
    if LlmChat is None or not EMERGENT_LLM_KEY:
        raise RuntimeError("Vision extraction provider is not configured")
    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"parse-{uuid.uuid4().hex}",
        system_message="You extract structured tax data from Indian financial documents.",
    ).with_model("gemini", "gemini-2.5-flash")
    raw = await chat.send_message(UserMessage(text=EXTRACTION_PROMPT, file_contents=file_contents))
    cleaned = re.sub(r"^```(json)?|```$", "", str(raw).strip(), flags=re.MULTILINE).strip()
    mo = re.search(r"\{.*\}", cleaned, re.DOTALL)
    data = json.loads(mo.group(0) if mo else cleaned)
    data["source"] = "gemini_vision"
    return data


async def parse_documents(files: list) -> dict:
    """files: list of {bytes, content_type, ext}. Consolidates all into one extraction."""
    base = {}
    tmp_paths = []
    file_contents = []
    try:
        for f in files:
            ext = (f.get("ext") or "").lower()
            ctype = f.get("content_type") or ("application/pdf" if ext == "pdf" else "image/jpeg")
            is_pdf = ext == "pdf" or ctype.endswith("pdf")
            if is_pdf:
                text = extract_text_local(f["bytes"])
                if text.strip():
                    base = _merge_regex(base, regex_extract(text))
            suffix = f".{ext}" if ext else (".pdf" if is_pdf else ".jpg")
            p = os.path.join(tempfile.gettempdir(), f"gp_{uuid.uuid4().hex}{suffix}")
            with open(p, "wb") as fh:
                fh.write(f["bytes"])
            tmp_paths.append(p)
            file_contents.append(FileContentWithMimeType(file_path=p, mime_type=ctype))

        gem = None
        try:
            gem = await _gemini_extract(file_contents)
        except Exception as e:
            logger.warning(f"Gemini unavailable, using local extraction: {e}")
    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except OSError:
                pass

    if gem and not gem.get("extraction_error"):
        merged = dict(base)
        for k, v in gem.items():
            if k in NUMERIC:
                if _num(v):
                    merged[k] = _num(v)
                elif k not in merged:
                    merged[k] = 0.0
            elif v not in (None, "", 0):
                merged[k] = v
        merged["source"] = "gemini+regex" if base else "gemini_vision"
        merged["pages_analyzed"] = len(files)
        data = merged
    elif base:
        base["pages_analyzed"] = len(files)
        data = base
    else:
        data = {"document_kind": "other", "confidence": 0.0, "pages_analyzed": len(files),
                "note": "Could not extract text locally; enable LLM budget for vision parsing of scanned images."}

    for k in NUMERIC:
        data[k] = _num(data.get(k, 0))
    conf = data.get("confidence", 0)
    try:
        conf = float(conf)
        data["confidence"] = round(conf * 100 if conf <= 1 else conf, 2)
    except Exception:
        data["confidence"] = 0.0
    return data


async def parse_document(file_bytes: bytes, content_type: str, ext: str) -> dict:
    return await parse_documents([{"bytes": file_bytes, "content_type": content_type, "ext": ext}])


# ---------------- PDF rendering & term-locating (CA desk) ----------------
def is_pdf_bytes(content_type: str, ext: str) -> bool:
    return (ext or "").lower() == "pdf" or (content_type or "").endswith("pdf")


def pdf_info(pdf_bytes: bytes, zoom: float = 2.0) -> dict:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        r = page.rect
        pages.append({"index": i, "width": round(r.width * zoom), "height": round(r.height * zoom)})
    count = doc.page_count
    doc.close()
    return {"page_count": count, "zoom": zoom, "pages": pages}


def render_page_png(pdf_bytes: bytes, page_index: int, zoom: float = 2.0) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    png = pix.tobytes("png")
    doc.close()
    return png


def _indian_group(n: int) -> str:
    s = str(abs(n))
    if len(s) <= 3:
        return s
    last3 = s[-3:]
    rest = s[:-3]
    parts = []
    while len(rest) > 2:
        parts.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        parts.insert(0, rest)
    return ",".join(parts) + "," + last3


def locate_term(pdf_bytes: bytes, term: str, zoom: float = 2.0) -> dict:
    """Search all pages for a term; return first page with hits and pixel rects."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    variants = [term]
    t = str(term).strip()
    if t.replace(".", "").replace(",", "").isdigit():
        num = t.split(".")[0].replace(",", "")
        try:
            iv = int(num)
            ind = _indian_group(iv)
            variants += [ind, f"{iv:,}", num, f"Rs. {ind}", f"Rs. {iv:,}", f"{iv:,.0f}"]
        except ValueError:
            pass
    seen = set()
    variants = [v for v in variants if v and not (v in seen or seen.add(v))]
    for i, page in enumerate(doc):
        for v in variants:
            rects = page.search_for(v)
            if rects:
                out = [[round(r.x0 * zoom), round(r.y0 * zoom), round(r.x1 * zoom), round(r.y1 * zoom)] for r in rects]
                doc.close()
                return {"page": i, "zoom": zoom, "rects": out, "matched": v}
    doc.close()
    return {"page": 0, "zoom": zoom, "rects": [], "matched": None}
