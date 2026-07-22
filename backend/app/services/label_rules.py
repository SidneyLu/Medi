from datetime import date, datetime
from typing import Any

CONDITION_ALIASES = {
    "过敏性鼻炎": "condition_allergic_rhinitis",
    "高血压": "condition_hypertension",
    "糖尿病": "condition_diabetes",
    "贫血": "condition_anemia",
}

ALLERGY_ALIASES = {
    "青霉素": "allergy_penicillin",
    "花粉": "allergy_pollen",
    "海鲜": "allergy_seafood",
}

MEDICATION_ALIASES = {
    "氯雷他定": "med_loratadine",
    "二甲双胍": "med_metformin",
    "胰岛素": "med_insulin",
}

SEX_LABELS = {
    "female": "女性",
    "male": "男性",
    "other": "其他",
    "unknown": "未说明",
}

PREGNANCY_LABELS = {
    "not_applicable": "不适用",
    "pregnant": "妊娠中",
    "postpartum": "产后",
    "unknown": "未说明",
}

TAG_LABELS = {
    "age_newborn": "新生儿",
    "age_child": "儿童",
    "age_adult": "成人",
    "age_older_adult": "老年",
    "sex_female": "女性",
    "sex_male": "男性",
    "sex_other": "其他性别",
    "sex_unknown": "性别未说明",
    "pregnancy_pregnant": "妊娠中",
    "pregnancy_postpartum": "产后",
}


def build_profile_tags(profile: dict[str, Any]) -> list[str]:
    tags: set[str] = set()
    birth_date = profile.get("birth_date")
    age = _calculate_age(birth_date)
    if age is not None:
        if age < 1:
            tags.add("age_newborn")
        elif age < 18:
            tags.add("age_child")
        elif age >= 65:
            tags.add("age_older_adult")
        else:
            tags.add("age_adult")

    sex = profile.get("sex_at_birth") or "unknown"
    tags.add(f"sex_{sex}")

    pregnancy_status = profile.get("pregnancy_status")
    if pregnancy_status and pregnancy_status not in {"unknown", "not_applicable"}:
        tags.add(f"pregnancy_{pregnancy_status}")

    bmi = _calculate_bmi(profile.get("height_cm"), profile.get("weight_kg"))
    if bmi is not None:
        if bmi < 18.5:
            tags.add("bmi_underweight")
        elif bmi < 24:
            tags.add("bmi_normal")
        elif bmi < 28:
            tags.add("bmi_overweight")
        else:
            tags.add("bmi_obesity")

    for field_name, prefix in (
        ("smoking_status", "smoking"),
        ("alcohol_use", "alcohol"),
        ("exercise_level", "exercise"),
        ("sleep_quality", "sleep"),
        ("diet_pattern", "diet"),
    ):
        value = str(profile.get(field_name) or "unknown").strip()
        if value and value != "unknown":
            tags.add(f"{prefix}_{value}")

    for value in profile.get("chronic_conditions", []):
        tags.add(CONDITION_ALIASES.get(value, f"condition_{_simple_slug(value)}"))
    for value in profile.get("allergies", []):
        tags.add(ALLERGY_ALIASES.get(value, f"allergy_{_simple_slug(value)}"))
    for value in profile.get("current_medications", []):
        tags.add(MEDICATION_ALIASES.get(value, f"med_{_simple_slug(value)}"))
    for value in profile.get("family_history", []):
        tags.add(f"family_history_{_simple_slug(value)}")
    for value in profile.get("recent_symptoms", []):
        tags.add(f"symptom_{_simple_slug(value)}")

    return sorted(tag for tag in tags if tag and not tag.endswith("_"))


def format_profile_context(profile: dict[str, Any] | None) -> str:
    """Human-readable profile summary for LLM personalization."""
    if not profile:
        return ""

    lines: list[str] = []
    nickname = str(profile.get("nickname") or "").strip()
    if nickname:
        lines.append(f"称呼：{nickname}")

    age = _calculate_age(profile.get("birth_date"))
    birth_date = str(profile.get("birth_date") or "").strip()
    if age is not None:
        lines.append(f"年龄：{age} 岁" + (f"（出生日期 {birth_date}）" if birth_date else ""))
    elif birth_date:
        lines.append(f"出生日期：{birth_date}")

    sex = profile.get("sex_at_birth") or "unknown"
    lines.append(f"出生性别：{SEX_LABELS.get(sex, sex)}")

    pregnancy = profile.get("pregnancy_status") or "unknown"
    if pregnancy not in {"unknown", "not_applicable"}:
        lines.append(f"妊娠状态：{PREGNANCY_LABELS.get(pregnancy, pregnancy)}")

    height = profile.get("height_cm")
    weight = profile.get("weight_kg")
    body_parts: list[str] = []
    if height is not None:
        body_parts.append(f"身高 {height} cm")
    if weight is not None:
        body_parts.append(f"体重 {weight} kg")
    if body_parts:
        lines.append("体格：" + "，".join(body_parts))

    conditions = [str(item).strip() for item in profile.get("chronic_conditions", []) if str(item).strip()]
    allergies = [str(item).strip() for item in profile.get("allergies", []) if str(item).strip()]
    medications = [str(item).strip() for item in profile.get("current_medications", []) if str(item).strip()]

    lines.append(f"已知慢性病或长期健康情况：{'、'.join(conditions) if conditions else '未记录'}")
    lines.append(f"过敏史：{'、'.join(allergies) if allergies else '未记录'}")
    lines.append(f"当前常用药：{'、'.join(medications) if medications else '未记录'}")

    return "\n".join(lines)


def humanize_profile_tags(tags: list[str]) -> list[str]:
    reverse_condition = {value: key for key, value in CONDITION_ALIASES.items()}
    reverse_allergy = {value: key for key, value in ALLERGY_ALIASES.items()}
    reverse_med = {value: key for key, value in MEDICATION_ALIASES.items()}
    labels: list[str] = []
    for tag in tags:
        if tag in TAG_LABELS:
            labels.append(TAG_LABELS[tag])
            continue
        if tag in reverse_condition:
            labels.append(f"慢病:{reverse_condition[tag]}")
            continue
        if tag in reverse_allergy:
            labels.append(f"过敏:{reverse_allergy[tag]}")
            continue
        if tag in reverse_med:
            labels.append(f"用药:{reverse_med[tag]}")
            continue
        if tag.startswith("condition_"):
            labels.append(f"慢病:{tag.removeprefix('condition_')}")
        elif tag.startswith("allergy_"):
            labels.append(f"过敏:{tag.removeprefix('allergy_')}")
        elif tag.startswith("med_"):
            labels.append(f"用药:{tag.removeprefix('med_')}")
        else:
            labels.append(tag)
    return labels


def _calculate_age(value: str | None) -> int | None:
    if not value:
        return None
    try:
        born = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _simple_slug(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    return "".join(ch for ch in normalized if ch.isalnum() or ch == "_")[:40]


def _calculate_bmi(height_cm: float | int | str | None, weight_kg: float | int | str | None) -> float | None:
    try:
        height = float(height_cm or 0)
        weight = float(weight_kg or 0)
    except (TypeError, ValueError):
        return None
    if height <= 0 or weight <= 0:
        return None
    height_m = height / 100
    return weight / (height_m * height_m)
