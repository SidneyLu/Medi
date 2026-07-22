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
