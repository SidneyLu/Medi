import base64
import json

import math
from typing import TYPE_CHECKING, Any

import httpx

from app.core.config import get_settings
from app.models.schemas import KnowledgeChunkData

if TYPE_CHECKING:
    from app.services.pdf_page_qa import PdfPageEvidence


VALID_RISK_LEVELS = {"low", "medium", "high", "unknown"}
REPORT_METADATA_NAME_KEYWORDS = {
    "姓名",
    "性别",
    "出生日期",
    "体检日期",
    "报告编号",
    "编号",
    "序号",
    "身份证",
    "手机",
    "电话",
    "医院",
    "科室",
    "医生",
    "地址",
    "页码",
}


class QwenClient:
    """Qwen chat adapter with a deterministic local fallback when no API key is configured."""

    def generate_answer(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_keywords: list[str] | None = None,
    ) -> dict:
        settings = get_settings()
        if not settings.qwen_api_key:
            return self._generate_placeholder(question, profile_tags, chunks, profile_keywords or [])
        return self._generate_with_qwen(question, profile_tags, chunks, profile_keywords or [], settings)

    def generate_answer_from_pdf_pages(
        self,
        question: str,
        profile_tags: list[str],
        pages: list["PdfPageEvidence"],
    ) -> dict:
        settings = get_settings()
        if not settings.qwen_api_key:
            return self._generate_pdf_placeholder(question, profile_tags, pages)
        return self._generate_with_qwen_vision(question, profile_tags, pages, settings)

    def extract_report_items_from_ocr(self, raw_text: str) -> list[dict]:
        settings = get_settings()
        if not settings.qwen_api_key:
            raise RuntimeError("未配置报告指标筛选模型 API Key，无法对图片 OCR 原文进行 AI 筛选。")

        sanitized_text = _sanitize_report_ocr_text_for_model(raw_text)
        if not sanitized_text:
            return []

        payload = {
            "model": settings.qwen_model,
            "messages": self._build_report_ocr_messages(sanitized_text),
            "temperature": 0,
            "max_tokens": 1200,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        }
        response_json = self._post_chat_completions(payload, settings, "Qwen report OCR filtering")
        content = _extract_message_content(response_json)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Qwen report OCR filtering content is not valid JSON") from exc
        return _validate_report_items_payload(parsed)

    def generate_report_analysis(
        self,
        profile_tags: list[str],
        items: list[dict],
        knowledge_context: list[dict],
        profile_keywords: list[str] | None = None,
    ) -> dict:
        settings = get_settings()
        if not settings.qwen_api_key:
            raise RuntimeError("未配置体检报告综合分析模型 API Key。")
        payload = {
            "model": settings.qwen_model,
            "messages": self._build_report_analysis_messages(profile_tags, profile_keywords or [], items, knowledge_context),
            "temperature": 0.2,
            "max_tokens": 1600,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        }
        response_json = self._post_chat_completions(payload, settings, "Qwen report analysis")
        content = _extract_message_content(response_json)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Qwen report analysis content is not valid JSON") from exc
        return _validate_report_analysis_payload(parsed)

    def _generate_placeholder(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_keywords: list[str] | None = None,
    ) -> dict:
        first_chunk = chunks[0]
        answer = (
            f"根据检索到的 MSD 授权知识，您的问题“{question}”主要与《{first_chunk.article_title}》中的"
            f"“{first_chunk.section_title}”相关。\n\n"
            "当前系统已经成功检索到相关医学资料，但大模型回答功能尚未正式接入，因此本阶段仅展示知识检索与引用结果，不提供具体诊断或个体化治疗方案。\n\n"
            "本系统仅用于健康科普，不能替代医生诊断。如果症状持续、加重或出现明显危险信号，请及时前往正规医疗机构就诊。"
        )
        suggestions = [
            "记录症状出现的时间、持续时长、诱因及缓解因素。",
            "整理既往病史、过敏史、当前用药和近期检查报告。",
            "可结合下方引用的 MSD 原文页面了解相关健康知识。",
            "如果症状持续、加重或影响正常生活，请及时咨询医生。",
        ]
        if profile_tags or profile_keywords:
            suggestions.insert(2, "可结合年龄、妊娠状态、过敏史及慢性疾病等个人情况进一步评估。")
        return {"answer": answer, "suggestions": suggestions, "risk_level": "low"}

    def _generate_pdf_placeholder(
        self,
        question: str,
        profile_tags: list[str],
        pages: list["PdfPageEvidence"],
    ) -> dict:
        page_numbers = [_page_pdf_number(page) for page in pages]
        page_label = "、".join(str(page_number) for page_number in page_numbers) if page_numbers else "未定位到有效页面"
        answer = (
            f"系统已通过本地知识索引定位到 MSD 原始 PDF 第 {page_label} 页。"
            "当前未配置视觉模型 API，因此尚未读取页面图片并生成正式医学科普回答。\n\n"
            f"您的问题是：“{question}”。本阶段仅展示 PDF 页面定位能力，不提供具体诊断、处方或个体化治疗方案。"
        )
        suggestions = [
            "可先查看下方引用页面对应的 MSD 原始 PDF 内容。",
            "如症状持续、加重或出现危险信号，请及时线下就医。",
            "后续配置视觉模型 API 后，系统会基于实际发送的 PDF 页面图片生成回答。",
        ]
        if profile_tags:
            suggestions.insert(1, "如需个体化判断，请结合年龄、妊娠状态、慢性病和用药等信息咨询医生。")
        return {"answer": answer, "suggestions": suggestions, "risk_level": "low"}

    def _generate_with_qwen(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_keywords: list[str],
        settings,
    ) -> dict:
        payload = {
            "model": settings.qwen_model,
            "messages": self._build_messages(question, profile_tags, profile_keywords, chunks[:5]),
            "temperature": 0.2,
            "max_tokens": 800,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        }
        response_json = self._post_chat_completions(payload, settings, "Qwen")
        content = _extract_message_content(response_json)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Qwen message content is not valid JSON") from exc
        return _validate_answer_payload(parsed)

    def _generate_with_qwen_vision(
        self,
        question: str,
        profile_tags: list[str],
        pages: list["PdfPageEvidence"],
        settings,
    ) -> dict:
        payload = {
            "model": getattr(settings, "qwen_vision_model", settings.qwen_model),
            "messages": self._build_vision_messages(question, profile_tags, pages),
            "temperature": 0.1,
            "max_tokens": 1000,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        }
        response_json = self._post_chat_completions(payload, settings, "Qwen vision")
        content = _extract_message_content(response_json)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Qwen vision message content is not valid JSON") from exc
        return _validate_answer_payload(parsed)

    def _post_chat_completions(self, payload: dict, settings, error_label: str) -> dict:
        url = f"{settings.qwen_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.qwen_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=settings.qwen_timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError(f"{error_label} request timed out") from exc
        except httpx.HTTPStatusError as exc:
            request_id = _request_id_from_response(exc.response)
            status_code = exc.response.status_code
            raise RuntimeError(f"{error_label} HTTP error: status_code={status_code}, request_id={request_id}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"{error_label} network error: {exc.__class__.__name__}") from exc

        try:
            return response.json()
        except ValueError as exc:
            request_id = _request_id_from_response(response)
            raise RuntimeError(f"{error_label} API response is not valid JSON: request_id={request_id}") from exc

    def _build_messages(
        self,
        question: str,
        profile_tags: list[str],
        profile_keywords: list[str],
        chunks: list[KnowledgeChunkData],
    ) -> list[dict]:
        system_prompt = (
            "你是Medi健康科普助手。\n"
            "只能依据用户问题和提供的MSD资料回答，不得使用资料之外的医学事实补全答案。\n"
            "回答要求：\n"
            "1. 使用简体中文。\n"
            "2. 直接回答用户问题。\n"
            "3. 不进行确诊。\n"
            "4. 不开具处方。\n"
            "5. 不擅自给出药物剂量。\n"
            "6. 不替代医生诊断。\n"
            "7. 资料不足时明确说明“当前检索资料不足以支持明确结论”。\n"
            "8. 存在明显危险信号时，提示及时线下就医或急诊。\n"
            "9. 不得声称已经查看用户未提供的检查报告。\n"
            "10. 不得编造来源、页码、疾病或检查结果。\n"
            "11. 返回内容必须是JSON对象，不得包含Markdown代码块。\n"
            "risk_level只能是low、medium、high、unknown。"
        )
        user_prompt = (
            f"用户问题：{question}\n\n"
            f"{self._format_profile_context(profile_tags, profile_keywords)}"
            "请基于以下资料回答。\n\n"
            f"{self._format_chunks(chunks)}\n\n"
            "请严格返回以下JSON格式：\n"
            '{"answer":"中文科普回答","suggestions":["建议1","建议2"],"risk_level":"low"}'
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_vision_messages(
        self,
        question: str,
        profile_tags: list[str],
        pages: list["PdfPageEvidence"],
    ) -> list[dict]:
        system_prompt = (
            "你是 Medi 健康科普助手。\n"
            "只能根据本次提供的 MSD 原始 PDF 页面图片作答。\n"
            "OCR文本仅用于检索定位，本次没有提供OCR正文，不得使用页面图片之外的医学知识补全答案。\n"
            "页面中无法确认的信息必须说明“当前提供的PDF页面不足以支持明确结论”。\n"
            "使用简体中文，不进行确诊，不开具处方，不提供个体化药物剂量，不替代医生诊断。\n"
            "不得编造页面内容、页码、检查结果或引用。引用依据时使用“PDF物理页第X页”。\n"
            "存在危险信号时建议及时线下就医或急诊。\n"
            "只返回JSON对象，不得返回Markdown代码块。"
        )
        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"用户问题：{question}\n"
                    f"{self._format_profile_tags(profile_tags)}"
                    "请阅读下面按检索顺序提供的 PDF 页面图片，并严格返回："
                    '{"answer":"中文科普回答","suggestions":["建议1","建议2"],"risk_level":"low"}'
                ),
            }
        ]
        for page in pages:
            user_content.append(
                {
                    "type": "text",
                    "text": (
                        f"[PDF物理页{_page_pdf_number(page)}] "
                        f"章节：{_page_section_title(page)}"
                    ),
                }
            )
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": _image_bytes_to_data_url(_page_image_bytes(page)),
                    },
                }
            )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    @staticmethod
    def _build_report_ocr_messages(raw_text: str) -> list[dict]:
        system_prompt = (
            "你是Medi体检报告OCR指标筛选器。\n"
            "你的唯一任务是从PaddleOCR识别出的原文中筛选真实存在的体检检查指标，并返回结构化JSON。\n"
            "只允许保留实验室检验指标、基础体征、有医学意义的客观检查数值和明确属于体检项目的定量结果。\n"
            "必须排除姓名、性别、年龄、出生日期、体检日期、报告编号、身份证号、手机号、医院名称、科室名称、医生姓名、地址、序号、编号、页码、条形码和文件名。\n"
            "不得判断疾病，不得给出诊断或治疗方案，不得判断是否超标，不得编造OCR原文中不存在的指标、数值、单位或参考范围。\n"
            "返回JSON对象，禁止Markdown代码块。JSON格式必须为："
            '{"items":[{"name":"白细胞计数","value":5.02,"unit":"10^9/L","reference_low":4.0,"reference_high":10.0}]}'
        )
        user_prompt = (
            "请从以下OCR原文中筛选体检指标。只返回JSON对象。\n\n"
            f"OCR原文：\n{raw_text}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _build_report_analysis_messages(
        profile_tags: list[str],
        profile_keywords: list[str],
        items: list[dict],
        knowledge_context: list[dict],
    ) -> list[dict]:
        system_prompt = (
            "你是Medi体检报告综合分析助手。\n"
            "全部使用简体中文。这是综合体检分析，不是逐指标解释器。\n"
            "不得逐条复述全部指标；优先分析high和low指标、接近报告参考边界的指标，以及有代表性的基础体征和检查。\n"
            "normal指标只做分类概括，不逐条罗列。unknown指标不得写成正常或异常。\n"
            "near_boundary只表示接近本报告参考边界，不是超标，不得称为疾病风险。\n"
            "后端提供的status是必须服从的事实，不得自行重新计算或推翻。\n"
            "报告参考范围优先于通用范围，MSD资料只用于解释健康意义，不得覆盖原报告参考范围。\n"
            "不得确诊、不得开处方、不得提供药物剂量、不得建议擅自停药或换药，不得编造症状、病史、生活习惯或用户未提供的信息。\n"
            "如果没有high或low指标，请说明“在本次成功提取且具有可比较参考范围的指标中，未发现明显超出报告参考范围的项目。”\n"
            "提醒用户OCR提取可能不完整，应以原始报告和医生意见为准。\n"
            "只返回JSON对象，不得返回Markdown代码块。"
        )
        user_prompt = (
            "请基于以下已确认体检指标、用户画像标签和MSD资料，生成一份自然、完整的中文体检综合分析。\n\n"
            f"用户画像标签：{profile_tags or []}\n"
            f"用户画像关键词：{profile_keywords or []}\n\n"
            f"已确认指标JSON：{json.dumps(items, ensure_ascii=False)}\n\n"
            f"MSD资料JSON：{json.dumps(knowledge_context, ensure_ascii=False)}\n\n"
            "请严格返回JSON格式："
            '{"overall_assessment":"整体健康情况中文总结","risk_level":"low","key_findings":[{"title":"标题","content":"内容"}],'
            '"normal_overview":"正常指标分类概括","lifestyle_advice":["建议1"],"follow_up_advice":["建议1"],'
            '"warning_signs":["需要及时关注的情况"],"disclaimer":"本报告仅用于健康科普，不能替代医生诊断。"}'
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _format_profile_context(profile_tags: list[str], profile_keywords: list[str]) -> str:
        if not profile_tags and not profile_keywords:
            return ""
        tags = "、".join(str(tag) for tag in profile_tags if str(tag).strip())
        keywords = "、".join(str(keyword) for keyword in profile_keywords if str(keyword).strip())
        lines: list[str] = []
        if tags:
            lines.append(f"用户画像标签：{tags}")
        if keywords:
            lines.append(f"用户画像关键词：{keywords}")
        return "\n".join(lines) + "\n\n"

    @staticmethod
    def _format_profile_tags(profile_tags: list[str]) -> str:
        return QwenClient._format_profile_context(profile_tags, [])

    @staticmethod
    def _format_chunks(chunks: list[KnowledgeChunkData]) -> str:
        lines: list[str] = []
        for index, chunk in enumerate(chunks, start=1):
            lines.append(
                "\n".join(
                    [
                        f"[资料{index}]",
                        f"article_title: {chunk.article_title}",
                        f"section_title: {chunk.section_title}",
                        f"source_url: {chunk.source_url}",
                        f"content: {chunk.content}",
                    ]
                )
            )
        return "\n\n".join(lines)


def _request_id_from_response(response: httpx.Response) -> str:
    request_id = response.headers.get("x-request-id") or response.headers.get("x-acs-request-id")
    if request_id:
        return request_id
    try:
        body = response.json()
    except ValueError:
        return "unknown"
    if isinstance(body, dict):
        for key in ("request_id", "requestId", "id"):
            value = body.get(key)
            if value:
                return str(value)
    return "unknown"


def _extract_message_content(response_json: dict) -> str:
    try:
        choices = response_json["choices"]
        if not choices:
            raise RuntimeError("Qwen API response choices is empty")
        content = choices[0]["message"]["content"]
    except (KeyError, TypeError, IndexError) as exc:
        raise RuntimeError("Qwen API response format is invalid: missing choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Qwen API response message.content is empty")
    return content.strip()


def _validate_answer_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("Qwen message JSON must be an object")
    answer = payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise RuntimeError("Qwen message JSON must include a non-empty answer")

    raw_suggestions = payload.get("suggestions", [])
    if raw_suggestions is None:
        raw_suggestions = []
    if not isinstance(raw_suggestions, list):
        raise RuntimeError("Qwen message JSON suggestions must be a list")
    suggestions = [item.strip() for item in raw_suggestions if isinstance(item, str) and item.strip()][:5]

    risk_level = payload.get("risk_level", "unknown")
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "unknown"

    return {
        "answer": answer.strip(),
        "suggestions": suggestions,
        "risk_level": risk_level,
    }


def _image_bytes_to_data_url(image_bytes: bytes) -> str:
    if not isinstance(image_bytes, (bytes, bytearray)) or not image_bytes:
        raise RuntimeError("PDF page evidence image_bytes is empty")
    encoded = base64.b64encode(bytes(image_bytes)).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _page_image_bytes(page: Any) -> bytes:
    return _page_value(page, "image_bytes")


def _page_pdf_number(page: Any) -> int:
    value = _page_value(page, "pdf_page")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("PDF page evidence pdf_page is invalid") from exc


def _page_section_title(page: Any) -> str:
    value = _page_value(page, "section_title")
    return str(value or "未命名章节")


def _page_value(page: Any, field_name: str) -> Any:
    if isinstance(page, dict):
        return page.get(field_name)
    return getattr(page, field_name)


def _sanitize_report_ocr_text_for_model(raw_text: str) -> str:
    lines: list[str] = []
    for line in str(raw_text or "").replace("\r", "\n").splitlines():
        normalized = " ".join(line.split()).strip()
        if not normalized:
            continue
        if _is_sensitive_identity_line(normalized):
            continue
        lines.append(normalized)
    return "\n".join(lines)


def _is_sensitive_identity_line(line: str) -> bool:
    compact = line.replace(" ", "")
    identity_keywords = {
        "姓名",
        "身份证",
        "电话",
        "手机",
        "地址",
        "报告编号",
        "条形码",
        "文件名",
    }
    return any(keyword in compact for keyword in identity_keywords)


def _validate_report_items_payload(payload: dict) -> list[dict]:
    if not isinstance(payload, dict):
        raise RuntimeError("Qwen report OCR JSON must be an object")
    raw_items = payload.get("items")
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raise RuntimeError("Qwen report OCR JSON items must be a list")

    items: list[dict] = []
    seen: set[tuple[str, float, str]] = set()
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise RuntimeError(f"Qwen report OCR item {index} must be an object")

        name = _validate_report_item_name(raw_item.get("name"), index)
        if _is_metadata_item_name(name):
            continue
        value = _validate_finite_number(raw_item.get("value"), f"items[{index}].value")
        unit = _validate_report_item_unit(raw_item.get("unit"), index)
        reference_low = _validate_optional_finite_number(raw_item.get("reference_low"), f"items[{index}].reference_low")
        reference_high = _validate_optional_finite_number(raw_item.get("reference_high"), f"items[{index}].reference_high")
        if reference_low is not None and reference_high is not None and reference_low > reference_high:
            raise RuntimeError(f"Qwen report OCR item {index} reference_low must be <= reference_high")

        key = (name.lower(), value, unit.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "reference_low": reference_low,
                "reference_high": reference_high,
            }
        )
    return items


def _validate_report_item_name(value: object, index: int) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"Qwen report OCR item {index} name must be a string")
    name = " ".join(value.split()).strip()
    if not name:
        raise RuntimeError(f"Qwen report OCR item {index} name must be non-empty")
    if len(name) > 60:
        raise RuntimeError(f"Qwen report OCR item {index} name is too long")
    return name


def _validate_report_item_unit(value: object, index: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"Qwen report OCR item {index} unit must be a string")
    unit = " ".join(value.split()).strip()
    if len(unit) > 24:
        raise RuntimeError(f"Qwen report OCR item {index} unit is too long")
    return unit


def _validate_optional_finite_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    return _validate_finite_number(value, field_name)


def _validate_finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"Qwen report OCR {field_name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"Qwen report OCR {field_name} must be finite")
    return number


def _is_metadata_item_name(name: str) -> bool:
    compact = name.replace(" ", "")
    return any(keyword in compact for keyword in REPORT_METADATA_NAME_KEYWORDS)


def _validate_report_analysis_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise RuntimeError("Qwen report analysis JSON must be an object")

    overall_assessment = _required_text(payload, "overall_assessment")
    if _looks_like_legacy_english_template(overall_assessment):
        raise RuntimeError("Qwen report analysis contains legacy English template text")

    risk_level = payload.get("risk_level", "unknown")
    if risk_level not in VALID_RISK_LEVELS:
        risk_level = "unknown"

    key_findings = _validate_key_findings(payload.get("key_findings", []))[:5]
    normal_overview = _optional_text(payload, "normal_overview")
    lifestyle_advice = _validate_text_list(payload.get("lifestyle_advice", []), "lifestyle_advice")[:6]
    follow_up_advice = _validate_text_list(payload.get("follow_up_advice", []), "follow_up_advice")[:5]
    warning_signs = _validate_text_list(payload.get("warning_signs", []), "warning_signs")[:5]
    disclaimer = _required_text(payload, "disclaimer")

    return {
        "overall_assessment": overall_assessment,
        "risk_level": risk_level,
        "key_findings": key_findings,
        "normal_overview": normal_overview,
        "lifestyle_advice": lifestyle_advice,
        "follow_up_advice": follow_up_advice,
        "warning_signs": warning_signs,
        "disclaimer": disclaimer,
    }


def _required_text(payload: dict, field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Qwen report analysis {field_name} must be a non-empty string")
    return _strip_code_fence(value.strip(), field_name)


def _optional_text(payload: dict, field_name: str) -> str:
    value = payload.get(field_name, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"Qwen report analysis {field_name} must be a string")
    return _strip_code_fence(value.strip(), field_name)


def _validate_key_findings(value: object) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError("Qwen report analysis key_findings must be a list")
    findings: list[dict] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RuntimeError(f"Qwen report analysis key_findings[{index}] must be an object")
        title = _required_text(item, "title")
        content = _required_text(item, "content")
        findings.append({"title": title, "content": content})
    return findings


def _validate_text_list(value: object, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"Qwen report analysis {field_name} must be a list")
    return [
        _strip_code_fence(item.strip(), field_name)
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _strip_code_fence(value: str, field_name: str) -> str:
    if "```" in value:
        raise RuntimeError(f"Qwen report analysis {field_name} must not contain Markdown code fences")
    return value


def _looks_like_legacy_english_template(value: str) -> bool:
    markers = (
        "is not reliably comparable",
        "Keep the original report",
        "Do not use a single item",
        "reference range recorded in this report",
    )
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in markers)
