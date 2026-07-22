from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.schemas import ProfileKeyword

try:
    import jieba
except Exception:  # pragma: no cover - optional tokenizer
    jieba = None


STOPWORDS = {
    "unknown",
    "not_applicable",
    "none",
    "其他",
    "未知",
    "无",
    "暂无",
    "没有",
    "不详",
}

TAG_LABELS = {
    "age_newborn": "新生儿",
    "age_child": "儿童",
    "age_adult": "成人",
    "age_older_adult": "老年人",
    "bmi_underweight": "体重偏低",
    "bmi_normal": "BMI正常",
    "bmi_overweight": "超重",
    "bmi_obesity": "肥胖",
    "pregnancy_pregnant": "妊娠",
    "pregnancy_postpartum": "产后",
    "smoking_current": "当前吸烟",
    "smoking_former": "既往吸烟",
    "alcohol_frequent": "经常饮酒",
    "exercise_low": "运动不足",
    "sleep_poor": "睡眠较差",
    "diet_high_salt": "高盐饮食",
    "diet_high_sugar": "高糖饮食",
    "diet_high_fat": "高脂饮食",
    "diet_irregular": "饮食不规律",
}

CATEGORY_WEIGHT = {
    "condition": 2.0,
    "symptom": 1.9,
    "medication": 1.7,
    "allergy": 1.6,
    "family_history": 1.5,
    "lifestyle": 1.3,
    "demographic": 1.1,
    "derived": 1.0,
}


@dataclass(frozen=True)
class KeywordCandidate:
    keyword: str
    category: str
    source: str
    score: float


def extract_profile_keywords(profile: dict[str, Any], tags: list[str], limit: int = 20) -> list[ProfileKeyword]:
    candidates: list[KeywordCandidate] = []
    candidates.extend(_keywords_from_tags(tags))
    candidates.extend(_keywords_from_values(profile.get("chronic_conditions", []), "condition", "chronic_conditions"))
    candidates.extend(_keywords_from_values(profile.get("allergies", []), "allergy", "allergies"))
    candidates.extend(_keywords_from_values(profile.get("current_medications", []), "medication", "current_medications"))
    candidates.extend(_keywords_from_values(profile.get("family_history", []), "family_history", "family_history"))
    candidates.extend(_keywords_from_values(profile.get("recent_symptoms", []), "symptom", "recent_symptoms"))
    candidates.extend(_keywords_from_lifestyle(profile))

    merged: dict[str, KeywordCandidate] = {}
    for item in candidates:
        keyword = _normalize_keyword(item.keyword)
        if not keyword or keyword in STOPWORDS:
            continue
        previous = merged.get(keyword)
        if previous is None or item.score > previous.score:
            merged[keyword] = KeywordCandidate(keyword, item.category, item.source, round(item.score, 3))

    ordered = _drop_substring_noise(sorted(merged.values(), key=lambda item: (-item.score, item.category, item.keyword)))
    return [
        ProfileKeyword(keyword=item.keyword, category=item.category, score=item.score, source=item.source)
        for item in ordered[:limit]
    ]


def _keywords_from_tags(tags: list[str]) -> list[KeywordCandidate]:
    candidates: list[KeywordCandidate] = []
    for tag in tags:
        label = TAG_LABELS.get(tag)
        if not label:
            continue
        category = "lifestyle" if tag.startswith(("smoking_", "alcohol_", "exercise_", "sleep_", "diet_")) else "derived"
        if tag.startswith("age_"):
            category = "demographic"
        candidates.append(_candidate(label, category, "profile_tags"))
    return candidates


def _keywords_from_values(values: Any, category: str, source: str) -> list[KeywordCandidate]:
    if not isinstance(values, list):
        return []
    candidates: list[KeywordCandidate] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        candidates.append(_candidate(text, category, source, bonus=0.2))
        tokens = _tokenize(text)
        if tokens:
            candidates.extend(_candidate(token, category, source) for token in tokens)
        else:
            candidates.append(_candidate(text, category, source))
    return candidates


def _keywords_from_lifestyle(profile: dict[str, Any]) -> list[KeywordCandidate]:
    mapping = {
        "smoking_status": {
            "current": "当前吸烟",
            "former": "既往吸烟",
            "never": "不吸烟",
        },
        "alcohol_use": {
            "none": "不饮酒",
            "occasional": "偶尔饮酒",
            "frequent": "经常饮酒",
        },
        "exercise_level": {
            "low": "运动不足",
            "moderate": "规律运动",
            "high": "高频运动",
        },
        "sleep_quality": {
            "good": "睡眠良好",
            "fair": "睡眠一般",
            "poor": "睡眠较差",
        },
        "diet_pattern": {
            "balanced": "均衡饮食",
            "high_salt": "高盐饮食",
            "high_sugar": "高糖饮食",
            "high_fat": "高脂饮食",
            "irregular": "饮食不规律",
        },
    }
    candidates: list[KeywordCandidate] = []
    for field_name, labels in mapping.items():
        value = profile.get(field_name)
        label = labels.get(str(value))
        if label:
            candidates.append(_candidate(label, "lifestyle", field_name))
    return candidates


def _candidate(keyword: str, category: str, source: str, bonus: float = 0.0) -> KeywordCandidate:
    return KeywordCandidate(keyword, category, source, CATEGORY_WEIGHT.get(category, 1.0) + bonus)


def _drop_substring_noise(items: list[KeywordCandidate]) -> list[KeywordCandidate]:
    result: list[KeywordCandidate] = []
    for item in items:
        if any(
            item.category == kept.category
            and item.keyword != kept.keyword
            and item.keyword in kept.keyword
            and len(kept.keyword) >= len(item.keyword) + 2
            for kept in result
        ):
            continue
        result.append(item)
    return result


def _tokenize(text: str) -> list[str]:
    normalized = re.sub(r"[,，;；、/|]+", " ", text.strip())
    if not normalized:
        return []
    if re.search(r"[\u4e00-\u9fff]", normalized) and jieba is not None:
        tokens = [token.strip() for token in jieba.lcut(normalized) if token.strip()]
    else:
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_+-]{2,}", normalized)
    joined = []
    for token in tokens:
        clean = _normalize_keyword(token)
        if len(clean) >= 2 and clean not in STOPWORDS:
            joined.append(clean)
    if not joined and normalized not in STOPWORDS:
        return [normalized]
    return joined


def _normalize_keyword(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())
    return value[:40]
