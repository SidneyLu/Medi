from app.models.schemas import KnowledgeChunkData


class QwenClient:
    """Qwen adapter placeholder.

    The first-stage backend keeps this deterministic so front-end integration
    can run without external model keys. Replace generate_answer with the real
    Qwen API call after prompt and compliance review are ready.
    """

    def generate_answer(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
    ) -> dict:
        evidence_titles = "、".join({chunk.article_title for chunk in chunks})
        first_chunk = chunks[0]
        answer = (
            f"基于已检索到的 MSD 授权知识块，问题“{question}”可先从“{evidence_titles}”相关内容理解。"
            f"当前最相关章节是《{first_chunk.article_title}》的“{first_chunk.section_title}”。"
            "本回答仅作健康科普参考，不构成诊断、处方或个体化治疗建议；如症状持续、加重或伴随明显不适，应及时就医。"
        )
        suggestions = [
            "记录症状出现时间、持续时长、诱因和缓解方式",
            "整理既往病史、过敏史、当前用药和最近检查报告",
            "将引用的 MSD 原文作为就医前科普资料查看",
        ]
        if profile_tags:
            suggestions.insert(1, "结合个人画像标签查看是否属于儿童、老人、孕产妇或慢病等特殊人群")
        return {"answer": answer, "suggestions": suggestions, "risk_level": "low"}
