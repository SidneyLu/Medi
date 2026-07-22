from __future__ import annotations

from dataclasses import dataclass
import math
import re
from pathlib import Path
from typing import Any

import fitz

from app.models.schemas import ReportItem
from app.services.qwen_client import QwenClient


RANGE_PATTERN = re.compile(
    r"(?P<low>[<>]?\d+(?:\.\d+)?)\s*(?:-|~|－|–|—|至|到)\s*(?P<high>[<>]?\d+(?:\.\d+)?)"
)
NUMBER_PATTERN = re.compile(r"(?P<flag>[<>])?(?P<value>\d+(?:\.\d+)?)")
DEFAULT_OCR_CONFIDENCE_THRESHOLD = 0.5
IMAGE_AI_NO_ITEMS_MESSAGE = "图片文字已识别，但未筛选出有效体检指标。"
HEADER_WORDS = {
    "项目",
    "名称",
    "结果",
    "单位",
    "参考",
    "范围",
    "英文",
    "缩写",
    "提示",
}


KNOWN_ITEM_ALIASES = {
    "WBC": "白细胞计数",
    "RBC": "红细胞计数",
    "HGB": "血红蛋白",
    "HB": "血红蛋白",
    "PLT": "血小板计数",
    "GLU": "葡萄糖",
    "ALT": "丙氨酸氨基转移酶",
    "AST": "天门冬氨酸氨基转移酶",
    "TC": "总胆固醇",
    "TG": "甘油三酯",
    "HDL-C": "高密度脂蛋白胆固醇",
    "LDL-C": "低密度脂蛋白胆固醇",
    "CREA": "肌酐",
    "UA": "尿酸",
    "UREA": "尿素",
}


class ReportIndicatorExtractor:
    def __init__(
        self,
        min_confidence: float = DEFAULT_OCR_CONFIDENCE_THRESHOLD,
        qwen_client: QwenClient | None = None,
    ) -> None:
        self.min_confidence = min_confidence
        self._ocr_engine: Any | None = None
        self.qwen_client = qwen_client or QwenClient()

    def extract(self, file_path: Path, content: bytes) -> tuple[str, list[ReportItem], str | None]:
        suffix = file_path.suffix.lower()
        is_image = suffix in {".jpg", ".jpeg", ".png"}
        error_message: str | None = None
        items: list[ReportItem] = []
        if suffix == ".pdf":
            try:
                raw_text = self._extract_pdf_text(content)
            except Exception as exc:
                raw_text = ""
                error_message = f"PDF text extraction failed: {exc}"
            if not raw_text.strip() and error_message is None:
                error_message = "PDF text layer is empty; image-only report OCR is not available in this runtime."
            items = self.parse_items(raw_text)
        elif is_image:
            raw_text, error_message = self._extract_image_text(file_path)
            if raw_text.strip() and error_message is None:
                items, error_message = self._extract_image_items_with_ai(raw_text)
        else:
            raw_text = _best_effort_decode(content)
            items = self.parse_items(raw_text)
        return raw_text, items, error_message

    def _extract_pdf_text(self, content: bytes) -> str:
        parts: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as document:
            for page in document:
                text = page.get_text("text")
                if text.strip():
                    parts.append(text)
        return clean_text("\n".join(parts))

    def _extract_image_text(self, file_path: Path) -> tuple[str, str | None]:
        try:
            ocr = self._get_ocr_engine()
        except ImportError:
            return "", "图片 OCR 需要安装 paddleocr 和 paddlepaddle。"
        except Exception as exc:
            return "", f"图片 OCR 初始化失败：{exc.__class__.__name__}"
        try:
            if hasattr(ocr, "predict"):
                result = ocr.predict(str(file_path))
            else:
                result = ocr.ocr(str(file_path), cls=True)
            lines = [
                line
                for line in _iter_paddle_lines(result)
                if line.text and line.confidence >= self.min_confidence
            ]
            raw_text = build_ocr_raw_text(lines)
            if not raw_text:
                return "", "图片 OCR 未识别到有效文字。"
            return raw_text, None
        except Exception as exc:
            return "", f"图片 OCR 识别失败：{exc.__class__.__name__}"

    def _get_ocr_engine(self) -> Any:
        if self._ocr_engine is not None:
            return self._ocr_engine
        from paddleocr import PaddleOCR

        try:
            self._ocr_engine = PaddleOCR(lang="ch", use_textline_orientation=True, device="cpu")
        except TypeError:
            self._ocr_engine = PaddleOCR(lang="ch", use_angle_cls=True, use_gpu=False)
        return self._ocr_engine

    def _extract_image_items_with_ai(self, raw_text: str) -> tuple[list[ReportItem], str | None]:
        try:
            ai_items = self.qwen_client.extract_report_items_from_ocr(raw_text)
            items = normalize_ai_report_items(ai_items)
        except RuntimeError as exc:
            return [], _safe_extraction_error(str(exc))
        if not items:
            return [], IMAGE_AI_NO_ITEMS_MESSAGE
        return items, None

    def parse_items(self, text: str) -> list[ReportItem]:
        items: list[ReportItem] = []
        seen: set[tuple[str, float | None, str]] = set()
        for line in iter_candidate_lines(text):
            item = parse_indicator_line(line)
            if item is None:
                continue
            key = (item.name.lower(), item.value, item.unit.lower())
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        return items


def normalize_ai_report_items(raw_items: list[dict]) -> list[ReportItem]:
    items: list[ReportItem] = []
    seen: set[tuple[str, float | None, str]] = set()
    for raw_item in raw_items:
        item = normalize_ai_report_item(raw_item)
        if item is None:
            continue
        key = (item.name.lower(), item.value, item.unit.lower())
        if key in seen:
            continue
        seen.add(key)
        items.append(item)
    return items


def normalize_ai_report_item(raw_item: dict) -> ReportItem | None:
    if not isinstance(raw_item, dict):
        raise RuntimeError("AI筛选结果中的指标必须是对象")
    name = normalize_ai_item_name(raw_item.get("name"))
    if not name or is_metadata_item_name(name):
        return None
    value = normalize_ai_number(raw_item.get("value"), "value")
    unit = normalize_ai_unit(raw_item.get("unit"))
    reference_low = normalize_optional_ai_number(raw_item.get("reference_low"), "reference_low")
    reference_high = normalize_optional_ai_number(raw_item.get("reference_high"), "reference_high")
    if reference_low is not None and reference_high is not None and reference_low > reference_high:
        raise RuntimeError("AI筛选结果中的参考范围不合法")
    return ReportItem(
        item_id="",
        name=name,
        value=value,
        unit=unit,
        reference_low=reference_low,
        reference_high=reference_high,
        status=calculate_indicator_status(value, reference_low, reference_high),
    )


def normalize_ai_item_name(value: Any) -> str:
    if not isinstance(value, str):
        raise RuntimeError("AI筛选结果中的指标名称必须是字符串")
    name = " ".join(value.split()).strip()
    if not name:
        raise RuntimeError("AI筛选结果中的指标名称不能为空")
    if len(name) > 60:
        raise RuntimeError("AI筛选结果中的指标名称过长")
    return name


def normalize_ai_unit(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError("AI筛选结果中的单位必须是字符串")
    unit = " ".join(value.split()).strip()
    if len(unit) > 24:
        raise RuntimeError("AI筛选结果中的单位过长")
    return unit


def normalize_optional_ai_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return normalize_ai_number(value, field_name)


def normalize_ai_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"AI筛选结果中的{field_name}必须是数字")
    number = float(value)
    if not math.isfinite(number):
        raise RuntimeError(f"AI筛选结果中的{field_name}必须是有限数字")
    return number


def calculate_indicator_status(
    value: float,
    reference_low: float | None,
    reference_high: float | None,
) -> str:
    if reference_low is None or reference_high is None:
        return "unknown"
    if value < reference_low:
        return "low"
    if value > reference_high:
        return "high"
    return "normal"


def is_metadata_item_name(name: str) -> bool:
    compact = name.replace(" ", "")
    metadata_keywords = {
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
    return any(keyword in compact for keyword in metadata_keywords)


def _safe_extraction_error(message: str) -> str:
    normalized = " ".join(str(message or "").split())
    if not normalized:
        return "图片体检指标 AI 筛选失败。"
    return normalized[:160]


def iter_candidate_lines(text: str) -> list[str]:
    normalized = clean_text(text)
    raw_lines = [line.strip() for line in normalized.splitlines()]
    candidates: list[str] = []
    for line in raw_lines:
        line = normalize_report_line(line)
        if len(line) < 3 or not any(ch.isdigit() for ch in line):
            continue
        if is_header_line(line):
            continue
        candidates.append(line)
    return candidates


def parse_indicator_line(line: str) -> ReportItem | None:
    range_match = list(RANGE_PATTERN.finditer(line))
    selected_range = range_match[-1] if range_match else None
    prefix = line[: selected_range.start()].strip() if selected_range else line
    value_match = find_result_value_match(prefix)
    if value_match is None:
        return None

    value = float(value_match.group("value"))
    value_flag = value_match.group("flag")
    name = clean_indicator_name(prefix[: value_match.start()])
    unit = clean_unit(prefix[value_match.end() :])
    if not name:
        return None

    reference_low: float | None = None
    reference_high: float | None = None
    if selected_range:
        reference_low = float(selected_range.group("low").lstrip("<>"))
        reference_high = float(selected_range.group("high").lstrip("<>"))

    status = "unknown"
    if reference_low is not None and reference_high is not None:
        if value_flag == "<" or value < reference_low:
            status = "low"
        elif value_flag == ">" or value > reference_high:
            status = "high"
        else:
            status = "normal"

    return ReportItem(
        item_id="",
        name=name,
        value=value,
        unit=unit,
        reference_low=reference_low,
        reference_high=reference_high,
        status=status,
    )


def find_result_value_match(prefix: str) -> re.Match[str] | None:
    for match in NUMBER_PATTERN.finditer(prefix):
        name = clean_indicator_name(prefix[: match.start()])
        if not name:
            continue
        next_char = prefix[match.end() : match.end() + 1]
        if next_char in {"^", "/"}:
            continue
        return match
    return None


def clean_text(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_report_line(line: str) -> str:
    line = line.replace("：", ":").replace("（", "(").replace("）", ")")
    line = re.sub(r"[|｜,，;；]+", " ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def is_header_line(line: str) -> bool:
    compact = line.replace(" ", "")
    return sum(1 for word in HEADER_WORDS if word in compact) >= 3


def clean_indicator_name(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^[序号\d\.\-_\s]+", "", value)
    value = re.sub(r"[:：]+$", "", value)
    value = re.sub(r"(?:^|\s)(H|L|HI|LO|↑|↓)$", "", value, flags=re.IGNORECASE)
    value = value.strip(" :：-_/")
    if not value:
        return ""
    alias = KNOWN_ITEM_ALIASES.get(value.upper())
    return alias or value[:60]


def clean_unit(value: str) -> str:
    value = re.sub(r"(?:^|\s)(H|L|HI|LO|↑|↓)(?:\s|$)", " ", value, flags=re.IGNORECASE)
    value = value.strip(" :：,，;；")
    if len(value) > 24:
        return ""
    return value


def _best_effort_decode(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if any(ch.isdigit() for ch in text):
            return clean_text(text)
    return ""


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    box: list[list[float]]


def _iter_paddle_lines(result: Any):
    if hasattr(result, "json"):
        json_value = result.json
        if callable(json_value):
            json_value = json_value()
        if isinstance(json_value, dict):
            yield from _iter_paddle_lines(json_value)
            return
    if isinstance(result, dict):
        nested_result = result.get("res")
        if isinstance(nested_result, dict):
            yield from _iter_paddle_lines(nested_result)
            return
        texts = pick_dict_value(result, "rec_texts", "texts")
        scores = pick_dict_value(result, "rec_scores", "scores")
        boxes = pick_dict_value(result, "rec_polys", "dt_polys", "boxes")
        if texts is None:
            texts = []
        if scores is None:
            scores = []
        if boxes is None:
            boxes = []
        for text, score, box in zip(texts, scores, boxes):
            normalized_text = clean_text(str(text))
            if normalized_text:
                yield OcrLine(
                    text=normalized_text,
                    confidence=normalize_confidence(score),
                    box=normalize_box(box),
                )
        return
    if isinstance(result, list):
        if is_legacy_paddle_line(result):
            text = clean_text(str(result[1][0]))
            if text:
                yield OcrLine(
                    text=text,
                    confidence=normalize_confidence(result[1][1]),
                    box=normalize_box(result[0]),
                )
            return
        for item in result:
            yield from _iter_paddle_lines(item)
    elif isinstance(result, tuple):
        if is_legacy_paddle_line(result):
            text = clean_text(str(result[1][0]))
            if text:
                yield OcrLine(
                    text=text,
                    confidence=normalize_confidence(result[1][1]),
                    box=normalize_box(result[0]),
                )
            return
        yield from _iter_paddle_lines(list(result))


def pick_dict_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def is_legacy_paddle_line(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    payload = value[1]
    return isinstance(payload, (list, tuple)) and len(payload) >= 2 and isinstance(payload[0], str)


def normalize_confidence(value: Any) -> float:
    if value is None:
        return 1.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_box(box: Any) -> list[list[float]]:
    if box is None:
        return zero_box()
    if hasattr(box, "tolist"):
        box = box.tolist()
    points: list[list[float]] = []
    for point in box:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                points.append([float(point[0]), float(point[1])])
            except (TypeError, ValueError):
                continue
    if len(points) >= 4:
        return points[:4]
    return zero_box()


def zero_box() -> list[list[float]]:
    return [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]


def build_ocr_raw_text(lines: list[OcrLine]) -> str:
    rows = group_ocr_rows(lines)
    row_text = [" ".join(line.text for line in row if line.text).strip() for row in rows]
    return clean_text("\n".join(text for text in row_text if text))


def group_ocr_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    ordered = sorted(lines, key=lambda line: (box_top(line.box), box_left(line.box)))
    rows: list[list[OcrLine]] = []
    for line in ordered:
        center_y = box_center_y(line.box)
        if rows and abs(center_y - average_center_y(rows[-1])) <= row_tolerance(rows[-1] + [line]):
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(row, key=lambda line: box_left(line.box)) for row in rows]


def row_tolerance(lines: list[OcrLine]) -> float:
    heights = [max(1.0, box_bottom(line.box) - box_top(line.box)) for line in lines]
    average_height = sum(heights) / len(heights) if heights else 12.0
    return max(8.0, average_height * 0.6)


def average_center_y(lines: list[OcrLine]) -> float:
    return sum(box_center_y(line.box) for line in lines) / len(lines)


def box_left(box: list[list[float]]) -> float:
    return min(point[0] for point in box)


def box_top(box: list[list[float]]) -> float:
    return min(point[1] for point in box)


def box_bottom(box: list[list[float]]) -> float:
    return max(point[1] for point in box)


def box_center_y(box: list[list[float]]) -> float:
    return (box_top(box) + box_bottom(box)) / 2
