from app.models.schemas import KnowledgeChunkData


class QwenClient:
    """Deterministic first-stage Qwen adapter.

    Replace this method with a real Qwen API call once prompts, citation checks,
    and compliance review are ready.
    """

    def generate_answer(
        self,
        question: str,
        profile_tags: list[str],
        chunks: list[KnowledgeChunkData],
    ) -> dict:
        first_chunk = chunks[0]
        answer = (
            f"Based on retrieved MSD knowledge, the question '{question}' is most related to "
            f"'{first_chunk.article_title}' / '{first_chunk.section_title}'. "
            "This response is for health education only and is not a diagnosis, prescription, "
            "or individualized treatment plan. If symptoms persist, worsen, or include warning "
            "signs, seek care from a qualified medical professional."
        )
        suggestions = [
            "Record symptom onset time, duration, triggers, and relieving factors.",
            "Prepare past medical history, allergy history, current medications, and recent test reports.",
            "Use the cited MSD source pages as background reading before visiting a clinician.",
        ]
        if profile_tags:
            suggestions.insert(1, "Review whether age, pregnancy, allergy, or chronic-condition tags change the discussion.")
        return {"answer": answer, "suggestions": suggestions, "risk_level": "low"}
