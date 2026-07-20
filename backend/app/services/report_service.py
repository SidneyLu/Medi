import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.responses import AppError
from app.models.schemas import Citation, ReportData, ReportItem, ReportItemsUpdateRequest, ReportListData, ReportType
from app.services.application_repository import ApplicationRepository
from app.services.knowledge_service import KnowledgeService
from app.services.profile_service import ProfileService
from app.services.report_indicator_extractor import ReportIndicatorExtractor
from app.services.storage import Store

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


class ReportService:
    def __init__(self, repository: ApplicationRepository, store: Store) -> None:
        self.repository = repository
        self.store = store
        self.settings = get_settings()
        self.profile_service = ProfileService(repository)
        self.knowledge_service = KnowledgeService(store)
        self.extractor = ReportIndicatorExtractor()

    def list_reports(self, user_id: str) -> ReportListData:
        return ReportListData(items=[self._to_report_data(item) for item in self.repository.list_reports(user_id)])

    def analyze(self, user_id: str, file_name: str, report_type: ReportType, content: bytes) -> ReportData:
        suffix = Path(file_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise AppError(status_code=400, code=40011, message="Only JPG, JPEG, PNG and PDF reports are supported")
        if not content:
            raise AppError(status_code=422, code=42201, message="Report file is required", error_type="validation_error")
        if len(content) > MAX_UPLOAD_BYTES:
            raise AppError(status_code=413, code=41301, message="Report file must be 15MB or smaller")

        report_id = str(uuid.uuid4())
        safe_file_name = f"{report_id}{suffix}"
        user_upload_dir = self.settings.upload_dir / user_id
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        saved_path = user_upload_dir / safe_file_name
        saved_path.write_bytes(content)

        profile_tags = self.profile_service.get_profile(user_id).tags
        raw_text, extracted_items, extraction_error = self.extractor.extract(saved_path, content)
        items = self._build_ocr_items(raw_text)
        if extracted_items:
            items = extracted_items
            for item in items:
                item.item_id = item.item_id or str(uuid.uuid4())
        created_at = self.repository.add_report(
            user_id=user_id,
            report_id=report_id,
            file_name=file_name,
            stored_file_name=safe_file_name,
            report_type=report_type,
            status="needs_confirmation",
            summary=None,
            profile_tags=profile_tags,
            items=[item.model_dump(exclude_none=True) for item in items],
            raw_text=raw_text,
            error_message=extraction_error,
        )
        self.repository.add_audit_log(
            user_id,
            "report.analyze",
            {
                "report_id": report_id,
                "file_name": file_name,
                "report_type": report_type,
                "items": len(items),
                "extraction_error": extraction_error,
            },
        )
        return ReportData(
            report_id=report_id,
            file_name=file_name,
            report_type=report_type,
            status="needs_confirmation",
            created_at=created_at,
            summary=None,
            profile_tags_used=profile_tags,
            items=items,
            error_message=extraction_error,
        )

    def get_report(self, user_id: str, report_id: str) -> ReportData:
        report = self.repository.get_report(user_id, report_id)
        if report is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        return self._to_report_data(report)

    def update_items(self, user_id: str, report_id: str, payload: ReportItemsUpdateRequest) -> ReportData:
        report = self.repository.update_report(
            user_id,
            report_id,
            status="needs_confirmation",
            items=[item.model_dump(exclude_none=True) for item in payload.items],
        )
        if report is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        self.repository.add_audit_log(user_id, "report.items.update", {"report_id": report_id, "items": len(payload.items)})
        return self._to_report_data(report)

    def interpret(self, user_id: str, report_id: str) -> ReportData:
        report = self.repository.get_report(user_id, report_id)
        if report is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")

        interpreted_items: list[dict] = []
        for item in report["items"]:
            report_item = ReportItem(**item)
            chunks = self.knowledge_service.search(report_item.name, limit=3)
            citations = [
                Citation(
                    chunk_id=chunk.chunk_id,
                    article_title=chunk.article_title,
                    section_title=chunk.section_title,
                    source_url=chunk.source_url,
                )
                for chunk in chunks
            ]
            status_text = {
                "low": "below",
                "high": "above",
                "normal": "within",
                "unknown": "not reliably comparable with",
            }[report_item.status]
            report_item.explanation = (
                f"{report_item.name} is {status_text} the reference range recorded in this report. "
                "This is health education only and must be interpreted with the original report, symptoms, "
                "sampling context, and a clinician's judgement."
            )
            report_item.suggestions = [
                "Keep the original report for follow-up visits.",
                "Do not use a single item as a diagnosis or prescription basis.",
            ]
            report_item.citations = citations
            interpreted_items.append(report_item.model_dump(exclude_none=True))

        summary = (
            "The report has been interpreted with the confirmed OCR items. Results are educational only, "
            "not a diagnosis, prescription, or individualized treatment plan."
        )
        updated = self.repository.update_report(
            user_id,
            report_id,
            status="completed",
            summary=summary,
            items=interpreted_items,
        )
        if updated is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        self.repository.add_audit_log(user_id, "report.interpret", {"report_id": report_id})
        return self._to_report_data(updated)

    def delete_report(self, user_id: str, report_id: str) -> None:
        if not self.repository.delete_report(user_id, report_id):
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        self.repository.add_audit_log(user_id, "report.delete", {"report_id": report_id})

    def _build_ocr_items(self, raw_text: str) -> list[ReportItem]:
        items = self.extractor.parse_items(raw_text)
        if not items:
            return [
                ReportItem(
                    item_id=str(uuid.uuid4()),
                    name="OCR pending",
                    value=None,
                    unit="",
                    reference_low=None,
                    reference_high=None,
                    status="unknown",
                )
            ]

        for item in items:
            item.item_id = item.item_id or str(uuid.uuid4())
        return items

    def _to_report_data(self, report: dict) -> ReportData:
        return ReportData(
            report_id=report["report_id"],
            file_name=report["file_name"],
            report_type=report["report_type"],
            status=report["status"],
            created_at=report["created_at"],
            summary=report.get("summary"),
            profile_tags_used=report.get("profile_tags_used", []),
            items=[ReportItem(**item) for item in report["items"]],
            error_message=report.get("error_message"),
        )


def _best_effort_text(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if any(ch.isdigit() for ch in text):
            return text
    return ""


def _parse_report_items(text: str) -> list[dict]:
    results: list[dict] = []
    patterns = [
        r"(?P<name>hemoglobin|hb|血红蛋白)\D{0,20}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>g/L|g/dL)?\D{0,20}(?P<low>\d+(?:\.\d+)?)\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)",
        r"(?P<name>glucose|blood sugar|血糖|葡萄糖)\D{0,20}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mmol/L)?\D{0,20}(?P<low>\d+(?:\.\d+)?)\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = float(match.group("value"))
            low = float(match.group("low"))
            high = float(match.group("high"))
            status = "normal"
            if value < low:
                status = "low"
            elif value > high:
                status = "high"
            results.append(
                {
                    "name": match.group("name"),
                    "value": value,
                    "unit": match.group("unit") or "",
                    "reference_low": low,
                    "reference_high": high,
                    "status": status,
                }
            )
    return results
