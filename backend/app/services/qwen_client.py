import json

import httpx

from app.core.config import get_settings
from app.models.schemas import KnowledgeChunkData


VALID_RISK_LEVELS = {"low", "medium", "high", "unknown"}


class QwenClient:
    """Qwen chat adapter with a deterministic local fallback when no API key is configured."""

    def generate_answer(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
    ) -> dict:
        settings = get_settings()
        if not settings.qwen_api_key:
            return self._generate_placeholder(question, profile_tags, chunks)
        return self._generate_with_qwen(question, profile_tags, chunks, settings)

    def _generate_placeholder(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
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
        if profile_tags:
            suggestions.insert(2, "可结合年龄、妊娠状态、过敏史及慢性疾病等个人情况进一步评估。")
        return {"answer": answer, "suggestions": suggestions, "risk_level": "low"}

    def _generate_with_qwen(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        settings,
    ) -> dict:
        url = f"{settings.qwen_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.qwen_model,
            "messages": self._build_messages(question, profile_tags, chunks[:5]),
            "temperature": 0.2,
            "max_tokens": 800,
            "enable_thinking": False,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {settings.qwen_api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=settings.qwen_timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Qwen request timed out") from exc
        except httpx.HTTPStatusError as exc:
            request_id = _request_id_from_response(exc.response)
            status_code = exc.response.status_code
            raise RuntimeError(f"Qwen HTTP error: status_code={status_code}, request_id={request_id}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Qwen network error: {exc.__class__.__name__}") from exc

        try:
            response_json = response.json()
        except ValueError as exc:
            request_id = _request_id_from_response(response)
            raise RuntimeError(f"Qwen API response is not valid JSON: request_id={request_id}") from exc

        content = _extract_message_content(response_json)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            request_id = _request_id_from_response(response)
            raise RuntimeError(f"Qwen message content is not valid JSON: request_id={request_id}") from exc
        return _validate_answer_payload(parsed)

    def _build_messages(
        self,
        question: str,
        profile_tags: list[str],
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
            f"{self._format_profile_tags(profile_tags)}"
            "请基于以下资料回答。\n\n"
            f"{self._format_chunks(chunks)}\n\n"
            "请严格返回以下JSON格式：\n"
            '{"answer":"中文科普回答","suggestions":["建议1","建议2"],"risk_level":"low"}'
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _format_profile_tags(profile_tags: list[str]) -> str:
        if not profile_tags:
            return ""
        tags = "、".join(str(tag) for tag in profile_tags if str(tag).strip())
        if not tags:
            return ""
        return f"用户画像标签：{tags}\n\n"

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
