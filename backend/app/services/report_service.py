import re
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.responses import AppError
from app.models.schemas import Citation, ReportAnalyzeData, ReportDetailData, ReportItem, ReportType
from app.services.knowledge_service import KnowledgeService
from app.services.profile_service import ProfileService
from app.services.storage import Store

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}


class ReportService:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.settings = get_settings()
        self.profile_service = ProfileService(store)
        self.knowledge_service = KnowledgeService(store)

    def analyze(self, user_id: str, file_name: str, report_type: ReportType, content: bytes) -> ReportAnalyzeData:
        suffix = Path(file_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise AppError(status_code=400, code=40011, message="Only JPG, JPEG, PNG and PDF reports are supported")
        if not content:
            raise AppError(status_code=400, code=40012, message="Uploaded report is empty")

        report_id = str(uuid.uuid4())
        safe_file_name = f"{report_id}{suffix}"
        user_upload_dir = self.settings.upload_dir / user_id
        user_upload_dir.mkdir(parents=True, exist_ok=True)
        (user_upload_dir / safe_file_name).write_bytes(content)

        profile_tags = self.profile_service.get_profile(user_id).tags
        raw_text = _best_effort_text(content)
        items = self._build_items(raw_text)
        summary = (
            "已保存报告并完成第一阶段结构化解读。当前 OCR 为可替换占位实现；"
            "正式接入 OCR 后会提取指标、单位、参考区间和采样时间，再结合 MSD 知识块生成解释。"
        )

        self.store.add_report(
            user_id=user_id,
            report_id=report_id,
            file_name=file_name,
            report_type=report_type,
            status="completed",
            summary=summary,
            items=[item.model_dump() for item in items],
        )
        self.store.add_audit_log(
            user_id,
            "report.analyze",
            {"report_id": report_id, "file_name": file_name, "report_type": report_type},
        )
        return ReportAnalyzeData(
            report_id=report_id,
            file_name=file_name,
            report_type=report_type,
            status="completed",
            summary=summary,
            profile_tags_used=profile_tags,
            items=items,
        )

    def get_report(self, user_id: str, report_id: str) -> ReportDetailData:
        report = self.store.get_report(user_id, report_id)
        if report is None:
            raise AppError(status_code=404, code=40401, message="Report not found")
        profile_tags = self.profile_service.get_profile(user_id).tags
        return ReportDetailData(
            report_id=report["report_id"],
            file_name=report["file_name"],
            report_type=report["report_type"],
            status=report["status"],
            summary=report["summary"],
            profile_tags_used=profile_tags,
            items=[ReportItem(**item) for item in report["items"]],
        )

    def _build_items(self, raw_text: str) -> list[ReportItem]:
        parsed = _parse_report_items(raw_text)
        if not parsed:
            return [
                ReportItem(
                    item_id=str(uuid.uuid4()),
                    name="OCR待接入",
                    value=None,
                    unit=None,
                    reference_low=None,
                    reference_high=None,
                    status="unknown",
                    explanation="未从文件中可靠提取到化验指标。第一阶段已保留上传与返回结构，后续接入 OCR 后填充真实指标。",
                    suggestions=["请确认图片清晰、包含指标名称、数值、单位和参考区间", "正式解读必须绑定 MSD 指标科普引用"],
                    citations=[],
                )
            ]

        items: list[ReportItem] = []
        for parsed_item in parsed:
            query = f"{parsed_item['name']} {parsed_item.get('status', '')}"
            chunks = self.knowledge_service.search(query, limit=3)
            citations = [
                Citation(
                    chunk_id=chunk.chunk_id,
                    article_title=chunk.article_title,
                    section_title=chunk.section_title,
                    source_url=chunk.source_url,
                )
                for chunk in chunks
            ]
            items.append(
                ReportItem(
                    item_id=str(uuid.uuid4()),
                    citations=citations,
                    explanation="该指标解释基于已检索知识块生成；正式版本需由 Qwen 在引用校验后输出。",
                    suggestions=["结合其他指标综合查看", "携带原报告咨询医生，不要只依据单项指标自行判断"],
                    **parsed_item,
                )
            )
        return items


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
        r"(?P<name>血红蛋白|hemoglobin|Hb)\D{0,20}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>g/L|g/dL)?\D{0,20}(?P<low>\d+(?:\.\d+)?)\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)",
        r"(?P<name>血糖|葡萄糖|glucose)\D{0,20}(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mmol/L)?\D{0,20}(?P<low>\d+(?:\.\d+)?)\s*[-~]\s*(?P<high>\d+(?:\.\d+)?)",
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
                    "unit": match.group("unit"),
                    "reference_low": low,
                    "reference_high": high,
                    "status": status,
                }
            )
    return results
