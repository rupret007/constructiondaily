"""Project document parsing and retrieval helpers for grounded copilot flows."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from .models import PlanSet, ProjectDocument, ProjectDocumentChunk
from .storage import (
    get_project_document_file_path,
    promote_project_document_to_safe,
    quarantine_project_document_file,
)

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "any",
    "are",
    "but",
    "can",
    "does",
    "for",
    "from",
    "how",
    "into",
    "its",
    "not",
    "our",
    "out",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "this",
    "those",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}
SPEC_QUESTION_KEYWORDS = ("spec", "specs", "specification", "specifications", "section", "sections")
ADDENDUM_QUESTION_KEYWORDS = ("addendum", "addenda")
RFI_QUESTION_KEYWORDS = ("rfi", "rfis", "request for information")
SUBMITTAL_QUESTION_KEYWORDS = ("submittal", "submittals", "shop drawing", "shop drawings")
VENDOR_QUESTION_KEYWORDS = ("vendor", "vendors", "manufacturer", "manufacturers", "model", "models", "cut sheet", "cutsheet")
SCOPE_QUESTION_KEYWORDS = ("scope", "scope letter", "bid instruction", "bid instructions")


def process_project_document(document: ProjectDocument) -> ProjectDocument:
    """Extract text and searchable chunks for a stored project document."""
    try:
        extracted_text, page_count, chunks = _extract_project_document_content(document)
        if not extracted_text.strip():
            raise RuntimeError("No extractable text was found in this document.")
    except Exception as exc:  # noqa: BLE001 - parser/runtime failures should stay user-visible, not 500
        return _mark_project_document_failed(document, exc)

    with transaction.atomic():
        document.storage_key = promote_project_document_to_safe(
            document.storage_key,
            str(document.project_id),
            str(document.plan_set_id) if document.plan_set_id else None,
        )
        document.page_count = page_count
        document.extracted_text = extracted_text
        document.parse_status = ProjectDocument.ParseStatus.PARSED
        document.parse_error = ""
        document.save(
            update_fields=[
                "storage_key",
                "page_count",
                "extracted_text",
                "parse_status",
                "parse_error",
                "updated_at",
            ]
        )
        document.chunks.all().delete()
        ProjectDocumentChunk.objects.bulk_create(
            [
                ProjectDocumentChunk(
                    document=document,
                    chunk_index=index,
                    page_number=chunk["page_number"],
                    content=chunk["content"],
                )
                for index, chunk in enumerate(chunks)
            ]
        )
    return document


def search_project_documents(
    *,
    project,
    question: str,
    plan_set: PlanSet | None = None,
    limit: int = 3,
) -> dict[str, Any]:
    query_tokens = _tokenize(question)
    documents = ProjectDocument.objects.filter(
        project=project,
        parse_status=ProjectDocument.ParseStatus.PARSED,
    ).select_related("plan_set")
    if plan_set is not None:
        documents = documents.filter(Q(plan_set=plan_set) | Q(plan_set__isnull=True))

    document_list = list(documents.prefetch_related("chunks"))
    if not document_list:
        return {"document_count": 0, "matches": []}

    if not query_tokens:
        return {"document_count": len(document_list), "matches": []}

    best_matches: dict[str, dict[str, Any]] = {}
    question_lower = question.lower()
    for document in document_list:
        title_lower = document.title.lower()
        for chunk in document.chunks.all():
            score = _score_chunk(
                content=chunk.content,
                title=title_lower,
                query_tokens=query_tokens,
                question_lower=question_lower,
                document=document,
                selected_plan_set=plan_set,
            )
            if score <= 0:
                continue
            key = str(document.id)
            candidate = {
                "document": document,
                "chunk": chunk,
                "score": score,
                "snippet": _snippet_from_content(chunk.content, query_tokens),
            }
            existing = best_matches.get(key)
            if existing is None or _match_sort_key(candidate) < _match_sort_key(existing):
                best_matches[key] = candidate

    matches = list(best_matches.values())
    matches.sort(
        key=_match_sort_key
    )
    return {"document_count": len(document_list), "matches": matches[:limit]}


def _mark_project_document_failed(document: ProjectDocument, exc: Exception) -> ProjectDocument:
    parse_error = str(exc).strip() or "Project document parsing failed."
    document.storage_key = quarantine_project_document_file(
        document.storage_key,
        str(document.project_id),
        str(document.plan_set_id) if document.plan_set_id else None,
    )
    document.page_count = 0
    document.extracted_text = ""
    document.parse_status = ProjectDocument.ParseStatus.FAILED
    document.parse_error = parse_error
    document.save(
        update_fields=[
            "storage_key",
            "page_count",
            "extracted_text",
            "parse_status",
            "parse_error",
            "updated_at",
        ]
    )
    document.chunks.all().delete()
    return document


def _created_at_sort_value(document: ProjectDocument) -> float:
    created_at = getattr(document, "created_at", None)
    if created_at is None:
        return 0.0
    return created_at.timestamp()


def _extract_project_document_content(document: ProjectDocument) -> tuple[str, int, list[dict[str, Any]]]:
    path = get_project_document_file_path(document.storage_key)
    if not path.exists():
        raise RuntimeError("Stored project document file was not found.")

    extension = (document.file_extension or "").lower()
    if extension == "pdf":
        pages = _extract_pdf_pages(path)
    elif extension in {"txt", "md"}:
        pages = _extract_text_pages(path)
    else:
        raise RuntimeError(f"Unsupported project document type '.{extension}'.")

    combined_text = "\n\n".join(page["content"] for page in pages if page["content"])
    chunks = _chunk_pages(pages)
    return combined_text, len(pages), chunks


def _extract_pdf_pages(path) -> list[dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to parse PDF project documents.") from exc

    pages: list[dict[str, Any]] = []
    ocr_command = _resolve_ocr_command()
    try:
        with fitz.open(path) as pdf:
            for page_number in range(pdf.page_count):
                page = pdf.load_page(page_number)
                text = _extract_page_text_with_optional_ocr(page, fitz, ocr_command=ocr_command)
                pages.append({"page_number": page_number + 1, "content": text})
    except Exception as exc:  # noqa: BLE001 - PyMuPDF raises parser-specific exceptions
        raise RuntimeError(f"PDF project document could not be parsed: {exc}") from exc
    if not any(page["content"] for page in pages) and settings.PRECONSTRUCTION_DOCUMENT_OCR_ENABLED and not ocr_command:
        raise RuntimeError(
            "No extractable text was found in this PDF. Install Tesseract or configure PRECONSTRUCTION_DOCUMENT_OCR_COMMAND to parse scanned PDFs."
        )
    return pages


def _extract_text_pages(path) -> list[dict[str, Any]]:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Text documents must be UTF-8 encoded.") from exc
    return [{"page_number": None, "content": _normalize_whitespace(raw_text)}]


def _normalize_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _chunk_pages(pages: list[dict[str, Any]], target_chars: int = 900) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        page_number = page["page_number"]
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page["content"]) if part.strip()]
        if not paragraphs and page["content"]:
            paragraphs = [page["content"]]
        buffer: list[str] = []
        buffer_len = 0
        for paragraph in paragraphs:
            paragraph_parts = _split_paragraph(paragraph, target_chars)
            for part in paragraph_parts:
                extra_len = len(part) + (2 if buffer else 0)
                if buffer and buffer_len + extra_len > target_chars:
                    chunks.append({"page_number": page_number, "content": "\n\n".join(buffer)})
                    buffer = [part]
                    buffer_len = len(part)
                else:
                    buffer.append(part)
                    buffer_len += extra_len
        if buffer:
            chunks.append({"page_number": page_number, "content": "\n\n".join(buffer)})
    return chunks


def _split_paragraph(paragraph: str, target_chars: int) -> list[str]:
    if len(paragraph) <= target_chars:
        return [paragraph]

    words = paragraph.split()
    if not words:
        return []
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for word in words:
        projected = current_len + len(word) + (1 if current else 0)
        if current and projected > target_chars:
            parts.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = projected
    if current:
        parts.append(" ".join(current))
    return parts


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9][a-z0-9-]*", text.lower())
    unique_tokens: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if (len(token) < 3 and not any(char.isdigit() for char in token)) or token in STOPWORDS or token in seen:
            continue
        unique_tokens.append(token)
        seen.add(token)
    return unique_tokens


def _score_chunk(
    *,
    content: str,
    title: str,
    query_tokens: list[str],
    question_lower: str,
    document: ProjectDocument,
    selected_plan_set: PlanSet | None,
) -> int:
    content_lower = content.lower()
    score = 0
    title_hits = 0
    for token in query_tokens:
        occurrences = content_lower.count(token)
        if occurrences:
            score += occurrences * 3
        if token in title:
            score += 4
            title_hits += 1
    if question_lower and question_lower in content_lower:
        score += 12
    if query_tokens:
        unique_hits = sum(1 for token in query_tokens if token in content_lower)
        score += unique_hits * 2
    if title_hits and title_hits == len(query_tokens):
        score += 6
    if score and any(f"section {token}" in content_lower for token in query_tokens if token.isdigit()):
        score += 2
    score += _document_scope_bonus(document, selected_plan_set)
    score += _document_type_bonus(document, question_lower)
    return score


def _snippet_from_content(content: str, query_tokens: list[str], max_chars: int = 220) -> str:
    normalized = " ".join(content.split())
    lower = normalized.lower()
    hit_positions = [lower.find(token) for token in query_tokens if lower.find(token) >= 0]
    start = max(0, min(hit_positions) - 60) if hit_positions else 0
    end = min(len(normalized), start + max_chars)
    snippet = normalized[start:end].strip()
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(normalized):
        snippet = f"{snippet}..."
    return snippet


def _match_sort_key(item: dict[str, Any]) -> tuple[float, float, int]:
    return (
        -item["score"],
        -_created_at_sort_value(item["document"]),
        item["chunk"].chunk_index,
    )


def _document_scope_bonus(document: ProjectDocument, selected_plan_set: PlanSet | None) -> int:
    if selected_plan_set is None:
        return 0
    if document.plan_set_id == selected_plan_set.id:
        return 8
    if document.plan_set_id is None:
        return 2
    return -4


def _document_type_bonus(document: ProjectDocument, question_lower: str) -> int:
    bonuses = {
        ProjectDocument.DocumentType.SPEC: SPEC_QUESTION_KEYWORDS,
        ProjectDocument.DocumentType.ADDENDUM: ADDENDUM_QUESTION_KEYWORDS,
        ProjectDocument.DocumentType.RFI: RFI_QUESTION_KEYWORDS,
        ProjectDocument.DocumentType.SUBMITTAL: SUBMITTAL_QUESTION_KEYWORDS,
        ProjectDocument.DocumentType.VENDOR: VENDOR_QUESTION_KEYWORDS,
        ProjectDocument.DocumentType.SCOPE: SCOPE_QUESTION_KEYWORDS,
    }
    keywords = bonuses.get(document.document_type, ())
    return 8 if any(keyword in question_lower for keyword in keywords) else 0


def _extract_page_text_with_optional_ocr(page, fitz_module, *, ocr_command: str | None) -> str:
    extracted_text = _normalize_whitespace(page.get_text("text"))
    if not _should_attempt_pdf_page_ocr(extracted_text):
        return extracted_text
    ocr_text = _run_pdf_page_ocr(page, fitz_module, ocr_command)
    ocr_text = _normalize_whitespace(ocr_text)
    if not ocr_text:
        return extracted_text
    if not extracted_text:
        return ocr_text
    if len(ocr_text) > len(extracted_text) + 8:
        return ocr_text
    if extracted_text.lower() in ocr_text.lower():
        return ocr_text
    if ocr_text.lower() in extracted_text.lower():
        return extracted_text
    return _normalize_whitespace(f"{extracted_text}\n\n{ocr_text}")


def _should_attempt_pdf_page_ocr(extracted_text: str) -> bool:
    if not settings.PRECONSTRUCTION_DOCUMENT_OCR_ENABLED:
        return False
    return len(extracted_text.strip()) < settings.PRECONSTRUCTION_DOCUMENT_OCR_MIN_TEXT_CHARS


def _resolve_ocr_command() -> str | None:
    if not settings.PRECONSTRUCTION_DOCUMENT_OCR_ENABLED:
        return None
    configured = settings.PRECONSTRUCTION_DOCUMENT_OCR_COMMAND.strip()
    if not configured:
        return None
    resolved = shutil.which(configured)
    if resolved:
        return resolved
    if shutil.which(configured.split()[0]):
        return configured
    return None


def _run_pdf_page_ocr(page, fitz_module, ocr_command: str | None) -> str:
    if not ocr_command:
        return ""
    scale = max(settings.PRECONSTRUCTION_DOCUMENT_OCR_SCALE, 1)
    matrix = fitz_module.Matrix(scale, scale)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=True) as image_file:
        pixmap.save(image_file.name)
        command = [ocr_command, image_file.name, "stdout", "--psm", "6"]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=settings.PRECONSTRUCTION_DOCUMENT_OCR_TIMEOUT_SECONDS,
                check=False,
            )
        except OSError:
            return ""
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""
