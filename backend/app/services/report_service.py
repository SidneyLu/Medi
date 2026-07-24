import math
import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.responses import AppError
from app.models.schemas import Citation, ReportData, ReportItem, ReportItemsUpdateRequest, ReportListData, ReportType
from app.services.application_repository import ApplicationRepository
from app.services.knowledge_service import KnowledgeService
from app.services.label_rules import humanize_profile_tags
from app.services.profile_service import ProfileService
from app.services.qwen_client import QwenClient
from app.services.report_indicator_extractor import ReportIndicatorExtractor, calculate_indicator_status
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
        self.qwen_client = QwenClient()

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

        profile_data = self.profile_service.get_profile(user_id)
        profile_tags = profile_data.tags
        profile_keywords = [item.keyword for item in profile_data.keywords]
        raw_text, extracted_items, extraction_error = self.extractor.extract(saved_path, content)
        is_image_report = suffix in {".jpg", ".jpeg", ".png"}
        if is_image_report:
            items = extracted_items or self._build_ocr_items("")
        else:
            items = extracted_items or self._build_ocr_items(raw_text)
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
                "profile_keywords": profile_keywords,
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
        items = [_with_recalculated_status(item).model_dump(exclude_none=True) for item in payload.items]
        report = self.repository.update_report(
            user_id,
            report_id,
            status="needs_confirmation",
            items=items,
        )
        if report is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        self.repository.add_audit_log(user_id, "report.items.update", {"report_id": report_id, "items": len(payload.items)})
        return self._to_report_data(report)

    def interpret(self, user_id: str, report_id: str) -> ReportData:
        report = self.repository.get_report(user_id, report_id)
        if report is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")

        report_items = [ReportItem(**item) for item in report["items"]]
        if not _has_usable_report_items(report_items):
            raise AppError(
                status_code=422,
                code=42202,
                message="No confirmed report indicators are available for interpretation",
                error_type="validation_error",
            )

        normalized_items = [_with_recalculated_status(item) for item in report_items if _is_real_report_item(item)]
        target_items = _select_knowledge_targets(normalized_items)
        knowledge_context, citations_by_item_id = self._build_report_knowledge_context(target_items)
        analysis_items = [_to_analysis_item(item) for item in normalized_items]
        profile_data = self.profile_service.get_profile(user_id)
        profile_tags = report.get("profile_tags_used", [])
        profile_keywords = [item.keyword for item in profile_data.keywords]
        ai_used = bool(self.settings.qwen_api_key)
        ai_success = False
        try:
            analysis = self.qwen_client.generate_report_analysis(
                profile_tags=profile_tags,
                profile_keywords=profile_keywords,
                items=analysis_items,
                knowledge_context=knowledge_context,
            )
            summary = format_report_analysis_summary(analysis)
            risk_level = analysis["risk_level"]
            ai_success = True
        except RuntimeError:
            summary = build_fallback_report_summary(analysis_items)
            risk_level = "unknown"

        interpreted_items = [
            _to_interpreted_item_dict(item, citations_by_item_id.get(item.item_id, []))
            for item in normalized_items
        ]
        updated = self.repository.update_report(
            user_id,
            report_id,
            status="completed",
            summary=summary,
            items=interpreted_items,
        )
        if updated is None:
            raise AppError(status_code=404, code=40402, message="Report not found", error_type="not_found")
        self.repository.add_audit_log(
            user_id,
            "report.interpret",
            {
                "report_id": report_id,
                "items": len(normalized_items),
                "abnormal_items": sum(1 for item in normalized_items if item.status in {"high", "low"}),
                "ai_used": ai_used,
                "ai_success": ai_success,
                "risk_level": risk_level,
                "profile_keywords": profile_keywords,
            },
        )
        return self._to_report_data(updated)

    def _build_report_knowledge_context(
        self,
        target_items: list[ReportItem],
    ) -> tuple[list[dict], dict[str, list[Citation]]]:
        context: list[dict] = []
        citations_by_item_id: dict[str, list[Citation]] = {}
        seen_chunk_ids: set[str] = set()
        for item in target_items:
            chunks = self.knowledge_service.search(_knowledge_query_for_item(item), limit=3)
            item_citations: list[Citation] = []
            for chunk in chunks:
                citation = Citation(
                    chunk_id=chunk.chunk_id,
                    article_title=chunk.article_title,
                    section_title=chunk.section_title,
                    source_url=chunk.source_url,
                )
                item_citations.append(citation)
                if chunk.chunk_id in seen_chunk_ids or len(context) >= 12:
                    continue
                seen_chunk_ids.add(chunk.chunk_id)
                context.append(
                    {
                        "chunk_id": chunk.chunk_id,
                        "article_title": chunk.article_title,
                        "section_title": chunk.section_title,
                        "content": chunk.content,
                        "source_url": chunk.source_url,
                    }
                )
            if item_citations:
                citations_by_item_id[item.item_id] = item_citations
            if len(context) >= 12:
                break
        return context, citations_by_item_id

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
            profile_tags_used=humanize_profile_tags(report.get("profile_tags_used", [])),
            items=[ReportItem(**item) for item in report["items"]],
            error_message=report.get("error_message"),
        )


def _with_recalculated_status(item: ReportItem) -> ReportItem:
    status = "unknown"
    if (
        _is_finite_number(item.value)
        and _is_finite_number(item.reference_low)
        and _is_finite_number(item.reference_high)
        and float(item.reference_low) <= float(item.reference_high)
    ):
        status = calculate_indicator_status(
            float(item.value),
            float(item.reference_low),
            float(item.reference_high),
        )
    return item.model_copy(update={"status": status})


def _is_finite_number(value: float | None) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _has_usable_report_items(items: list[ReportItem]) -> bool:
    return any(_is_real_report_item(item) for item in items)


def _is_real_report_item(item: ReportItem) -> bool:
    return bool(item.name.strip()) and item.name.strip().lower() != "ocr pending"


def _to_analysis_item(item: ReportItem) -> dict:
    return {
        "name": item.name,
        "value": item.value,
        "unit": item.unit,
        "reference_low": item.reference_low,
        "reference_high": item.reference_high,
        "status": item.status,
        "near_boundary": _is_near_boundary(item),
    }


def _is_near_boundary(item: ReportItem) -> bool:
    if item.status != "normal":
        return False
    if not (
        _is_finite_number(item.value)
        and _is_finite_number(item.reference_low)
        and _is_finite_number(item.reference_high)
    ):
        return False
    value = float(item.value)
    low = float(item.reference_low)
    high = float(item.reference_high)
    width = high - low
    if width <= 0 or value < low or value > high:
        return False
    return min(value - low, high - value) / width <= 0.10


def _select_knowledge_targets(items: list[ReportItem]) -> list[ReportItem]:
    selected: list[ReportItem] = []
    selected.extend(item for item in items if item.status in {"high", "low"})
    selected.extend(item for item in items if item.status == "normal" and _is_near_boundary(item))
    if not selected:
        selected.extend(item for item in items if item.status == "normal" and item.value is not None)
    if not selected:
        selected.extend(item for item in items if item.status == "unknown")
    return _dedupe_items(selected)[:6]


def _dedupe_items(items: list[ReportItem]) -> list[ReportItem]:
    result: list[ReportItem] = []
    seen: set[str] = set()
    for item in items:
        key = item.item_id or f"{item.name}:{item.value}:{item.unit}"
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _knowledge_query_for_item(item: ReportItem) -> str:
    if item.status == "high":
        return f"{item.name} 偏高 健康意义"
    if item.status == "low":
        return f"{item.name} 偏低 健康意义"
    return f"{item.name} 检查结果 参考范围 健康意义"


def _to_interpreted_item_dict(item: ReportItem, citations: list[Citation]) -> dict:
    clean_item = item.model_copy(
        update={
            "explanation": None,
            "suggestions": None,
            "citations": citations or None,
        }
    )
    return clean_item.model_dump(exclude_none=True)


def format_report_analysis_summary(analysis: dict) -> str:
    parts = [
        f"【综合评价】\n{analysis['overall_assessment']}",
    ]
    if analysis["key_findings"]:
        finding_lines = []
        for index, finding in enumerate(analysis["key_findings"], start=1):
            finding_lines.append(f"{index}. {finding['title']}\n{finding['content']}")
        parts.append("【重点关注】\n" + "\n\n".join(finding_lines))
    else:
        parts.append("【重点关注】\n本次未发现需要单独提示的项目。")
    if analysis["normal_overview"]:
        parts.append(f"【正常指标概览】\n{analysis['normal_overview']}")
    if analysis["lifestyle_advice"]:
        parts.append("【生活方式建议】\n" + _numbered_lines(analysis["lifestyle_advice"]))
    if analysis["follow_up_advice"]:
        parts.append("【复查与就医建议】\n" + _numbered_lines(analysis["follow_up_advice"]))
    if analysis["warning_signs"]:
        parts.append("【需要及时关注的情况】\n" + _numbered_lines(analysis["warning_signs"]))
    parts.append(f"【风险等级】\n{_risk_level_label(analysis['risk_level'])}")
    parts.append(f"【说明】\n{analysis['disclaimer']}")
    return "\n\n".join(parts)


def build_fallback_report_summary(items: list[dict]) -> str:
    abnormal = [item for item in items if item["status"] in {"high", "low"}]
    unknown = [item for item in items if item["status"] == "unknown"]
    focus_lines: list[str] = []
    if abnormal:
        for item in abnormal[:8]:
            value = item["value"] if item["value"] is not None else "-"
            focus_lines.append(f"- {item['name']}：{_status_label(item['status'])}，结果 {value} {item['unit']}")
    else:
        focus_lines.append("- 在本次成功提取且具有可比较参考范围的指标中，未发现明显超出报告参考范围的项目。")
    if unknown:
        focus_lines.append(f"- 另有 {len(unknown)} 项指标缺少完整参考范围，暂不能判断是否超出报告范围。")
    return "\n\n".join(
        [
            "【综合评价】\n本次报告已完成指标整理，但智能综合分析暂时不可用。",
            "【重点关注】\n" + "\n".join(focus_lines),
            "【建议】\n建议结合原始报告和医生意见进行确认。",
            "【说明】\n本结果仅用于健康信息整理，不构成诊断或治疗建议。",
        ]
    )


def _numbered_lines(values: list[str]) -> str:
    return "\n".join(f"{index}. {value}" for index, value in enumerate(values, start=1))


def _risk_level_label(value: str) -> str:
    return {
        "low": "低",
        "medium": "中",
        "high": "高",
        "unknown": "暂无法判断",
    }.get(value, "暂无法判断")


def _status_label(value: str) -> str:
    return {
        "high": "偏高",
        "low": "偏低",
        "normal": "范围内",
        "unknown": "待确认",
    }.get(value, "待确认")


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
