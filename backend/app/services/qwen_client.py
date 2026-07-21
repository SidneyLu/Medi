import json

import httpx

from app.core.config import get_settings
from app.models.schemas import KnowledgeChunkData


VALID_RISK_LEVELS = {"low", "medium", "high", "unknown"}
MAX_HISTORY_MESSAGES = 8
MAX_ASSISTANT_HISTORY_CHARS = 420


class QwenClient:
    """Qwen chat adapter with a deterministic local fallback when no API key is configured."""

    def generate_answer(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_context: str = "",
        history: list[dict] | None = None,
    ) -> dict:
        settings = get_settings()
        history = history or []
        if not settings.qwen_api_key:
            return self._generate_placeholder(question, profile_tags, chunks, profile_context, history)
        return self._generate_with_qwen(question, profile_tags, chunks, profile_context, history, settings)

    def _generate_placeholder(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_context: str = "",
        history: list[dict] | None = None,
    ) -> dict:
        first_chunk = chunks[0]
        history = history or []

        status_lines = ["【本地联调自检】当前未配置大模型 API Key，以下用于验证功能是否接通（非正式模型回答）："]
        if profile_context.strip():
            status_lines.append("健康画像：已启用，并已读入表单内容")
            status_lines.append(profile_context.strip())
        elif profile_tags:
            status_lines.append("健康画像：已启用（标签）" + "、".join(profile_tags))
        else:
            status_lines.append("健康画像：本轮未启用或未填写")

        if history:
            prior_users = [
                str(item.get("content") or "").strip()
                for item in history
                if item.get("role") == "user" and str(item.get("content") or "").strip()
            ]
            status_lines.append(f"多轮记忆：已启用，已载入历史消息 {len(history)} 条")
            if prior_users:
                status_lines.append("本会话最近用户提问：" + " | ".join(prior_users[-3:]))
        else:
            status_lines.append("多轮记忆：本轮未启用（或无可载入历史）")

        status_lines.append(
            f"知识检索：命中《{first_chunk.article_title}》/ {first_chunk.section_title}"
        )
        status_lines.append(f"本轮问题：{question}")
        status_lines.append(
            f"资料摘录：{first_chunk.content[:220].strip()}"
            f"{'…' if len(first_chunk.content) > 220 else ''}"
        )
        status_lines.append(
            "若要得到真正的个性化生成回答，请在 backend/.env 配置 DASHSCOPE_API_KEY 后重启后端。"
        )

        answer = "\n".join(status_lines)
        suggestions = [
            "可切换「使用健康画像 / 使用多轮会话记忆」勾选后再问一轮，对比自检区变化。",
            "配置 DASHSCOPE_API_KEY 后即可验证完整大模型回答。",
            "本系统仅供健康科普，不能替代医生诊断。",
        ]
        if history:
            suggestions.insert(0, "取消勾选多轮记忆后再追问，自检区应显示“多轮记忆：本轮未启用”。")
        if profile_context.strip() or profile_tags:
            suggestions.insert(0, "取消勾选健康画像后再提问，自检区应显示“健康画像：本轮未启用”。")
        return {"answer": answer, "suggestions": suggestions[:5], "risk_level": "low"}

    def _generate_with_qwen(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
        profile_context: str,
        history: list[dict],
        settings,
    ) -> dict:
        url = f"{settings.qwen_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": settings.qwen_model,
            "messages": self._build_messages(question, profile_tags, chunks[:5], profile_context, history),
            "temperature": 0.2,
            "max_tokens": 900,
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
        profile_context: str = "",
        history: list[dict] | None = None,
    ) -> list[dict]:
        system_prompt = (
            "你是Medi健康科普助手。\n"
            "只能依据用户问题、会话历史（若提供）、用户健康画像（若提供）和提供的MSD资料回答，"
            "不得使用资料之外的医学事实补全答案。\n"
            "回答要求：\n"
            "1. 使用简体中文。\n"
            "2. 直接回答用户本轮问题，并正确理解指代（如“这个”“刚才”“还有呢”）。\n"
            "3. 若提供了会话历史，保持多轮连贯；不得编造历史中未出现的症状或检查结果。\n"
            "4. 若提供了健康画像，必须结合年龄/性别/妊娠状态/慢病/过敏/用药给出个性化科普提示。\n"
            "5. 不进行确诊。\n"
            "6. 不开具处方。\n"
            "7. 不擅自给出药物剂量。\n"
            "8. 不替代医生诊断。\n"
            "9. 资料不足时明确说明“当前检索资料不足以支持明确结论”。\n"
            "10. 存在明显危险信号时，提示及时线下就医或急诊。\n"
            "11. 不得声称已经查看用户未提供的检查报告。\n"
            "12. 不得编造来源、页码、疾病或检查结果。\n"
            "13. 返回内容必须是JSON对象，不得包含Markdown代码块。\n"
            "risk_level只能是low、medium、high、unknown。"
        )
        user_prompt = (
            f"{self._format_history_block(history or [])}"
            f"用户本轮问题：{question}\n\n"
            f"{self._format_profile_block(profile_context, profile_tags)}"
            "请基于以下资料回答；如有会话历史与画像，请一并体现连贯性与个性化。\n\n"
            f"{self._format_chunks(chunks)}\n\n"
            "请严格返回以下JSON格式：\n"
            '{"answer":"中文科普回答","suggestions":["建议1","建议2"],"risk_level":"low"}'
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _format_history_block(history: list[dict]) -> str:
        if not history:
            return ""
        lines = ["近期会话记忆（用于理解追问与指代，不得编造未出现内容）："]
        for item in history:
            role = item.get("role")
            content = str(item.get("content") or "").strip()
            if not content or role not in {"user", "assistant"}:
                continue
            label = "用户" if role == "user" else "助手"
            if role == "assistant" and len(content) > MAX_ASSISTANT_HISTORY_CHARS:
                content = content[:MAX_ASSISTANT_HISTORY_CHARS] + "…"
            lines.append(f"{label}：{content}")
        if len(lines) == 1:
            return ""
        return "\n".join(lines) + "\n\n"

    @staticmethod
    def _format_profile_block(profile_context: str, profile_tags: list[str]) -> str:
        parts: list[str] = []
        if profile_context.strip():
            parts.append("用户健康画像（来自个人信息表单，请用于个性化科普）：\n" + profile_context.strip())
        if profile_tags:
            tags = "、".join(str(tag) for tag in profile_tags if str(tag).strip())
            if tags:
                parts.append(f"画像标签：{tags}")
        if not parts:
            return "用户健康画像：本次未启用或尚未填写。\n\n"
        return "\n".join(parts) + "\n\n"

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
