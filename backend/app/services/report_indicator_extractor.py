from __future__ import annotations

from dataclasses import dataclass
import math
import re
import threading
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
# Dense scanned tables are slow on CPU; prefer smaller side length over hard timeouts.
OCR_MAX_IMAGE_SIDE = 1600
IMAGE_AI_NO_ITEMS_MESSAGE = "图片文字已识别，但未筛选出有效体检指标。"
_OCR_ENGINE_LOCK = threading.Lock()
_SHARED_OCR_ENGINE: Any | None = None
_OCR_WARMUP_STARTED = False


def warm_up_ocr_engine(background: bool = True) -> None:
    """Load PaddleOCR into memory once so the first upload is not a cold start."""

    global _OCR_WARMUP_STARTED
    if _OCR_WARMUP_STARTED and _SHARED_OCR_ENGINE is not None:
        return
    _OCR_WARMUP_STARTED = True

    def _load() -> None:
        try:
            ReportIndicatorExtractor()._get_ocr_engine()
        except Exception:
            # Warm-up is best-effort; upload path still reports real errors.
            pass

    if background:
        threading.Thread(target=_load, name="paddleocr-warmup", daemon=True).start()
    else:
        _load()


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
            elif raw_text.strip():
                # Keep rule-based items even when OCR reported a soft warning.
                items = self.parse_items(raw_text)
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
        # Match classmate behavior: wait for OCR to finish (no hard timeout that
        # falsely marks a slow-but-working scan as failed).
        ocr_path = self._prepare_ocr_image(file_path)
        cleanup_path = ocr_path if ocr_path != file_path else None
        try:
            ocr = self._get_ocr_engine()
            result = self._run_ocr(ocr, ocr_path)
            lines = [
                line
                for line in _iter_paddle_lines(result)
                if line.text and line.confidence >= self.min_confidence
            ]
            raw_text = build_ocr_raw_text(lines)
            if not raw_text:
                return "", "图片 OCR 未识别到有效文字。复杂表格/印章可能导致识别为空，可裁剪检验区后重试或手工填写。"
            return raw_text, None
        except ImportError:
            return "", "图片 OCR 需要安装 paddleocr 和 paddlepaddle。"
        except Exception as exc:
            return "", _safe_extraction_error(f"图片 OCR 识别失败：{exc.__class__.__name__}")
        finally:
            if cleanup_path and cleanup_path.exists():
                try:
                    cleanup_path.unlink()
                except OSError:
                    pass

    def _run_ocr(self, ocr: Any, file_path: Path) -> Any:
        if hasattr(ocr, "predict"):
            result = ocr.predict(str(file_path))
        else:
            result = ocr.ocr(str(file_path), cls=True)
        if result is None:
            return []
        return result

    def _prepare_ocr_image(self, file_path: Path) -> Path:
        """Downscale huge photos so CPU OCR does not freeze the machine."""
        try:
            from PIL import Image

            with Image.open(file_path) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                longest = max(width, height)
                if longest <= OCR_MAX_IMAGE_SIDE:
                    return file_path
                scale = OCR_MAX_IMAGE_SIDE / float(longest)
                resized = rgb.resize((max(1, int(width * scale)), max(1, int(height * scale))))
                output = file_path.with_name(f"{file_path.stem}_ocr_resized.jpg")
                resized.save(output, format="JPEG", quality=85, optimize=True)
                return output
        except Exception:
            return file_path

    def _get_ocr_engine(self) -> Any:
        global _SHARED_OCR_ENGINE
        if _SHARED_OCR_ENGINE is not None:
            return _SHARED_OCR_ENGINE
        with _OCR_ENGINE_LOCK:
            if _SHARED_OCR_ENGINE is not None:
                return _SHARED_OCR_ENGINE
            from paddleocr import PaddleOCR

            # Keep the pipeline minimal: det+rec only. Doc orientation / UVDoc
            # are heavy and unnecessary for typical lab-report photos.
            try:
                engine = PaddleOCR(
                    lang="ch",
                    device="cpu",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
            except TypeError:
                try:
                    engine = PaddleOCR(lang="ch", use_angle_cls=False, use_gpu=False)
                except TypeError:
                    engine = PaddleOCR(lang="ch")
            _SHARED_OCR_ENGINE = engine
            return _SHARED_OCR_ENGINE

    def _extract_image_items_with_ai(self, raw_text: str) -> tuple[list[ReportItem], str | None]:
        try:
            ai_items = self.qwen_client.extract_report_items_from_ocr(raw_text)
            items = normalize_ai_report_items(ai_items)
        except RuntimeError as exc:
            fallback = self.parse_items(raw_text)
            if fallback:
                return fallback, f"AI 指标筛选失败，已改用规则解析：{_safe_extraction_error(str(exc))}"
            return [], _safe_extraction_error(str(exc))
        if not items:
            fallback = self.parse_items(raw_text)
            if fallback:
                return fallback, IMAGE_AI_NO_ITEMS_MESSAGE + "已改用规则解析。"
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
    """Yield OCR lines from paddleocr 2.x / 3.x payloads without raising on odd shapes."""
    if result is None:
        return
    try:
        yield from _iter_paddle_lines_unsafe(result)
    except (IndexError, TypeError, KeyError, ValueError, AttributeError):
        return


def _iter_paddle_lines_unsafe(result: Any):
    if hasattr(result, "json"):
        json_value = result.json
        if callable(json_value):
            json_value = json_value()
        if isinstance(json_value, dict):
            yield from _iter_paddle_lines_unsafe(json_value)
            return
    if isinstance(result, dict):
        nested_result = result.get("res")
        if isinstance(nested_result, dict):
            yield from _iter_paddle_lines_unsafe(nested_result)
            return
        # Some paddlex versions nest OCR fields under "data".
        nested_data = result.get("data")
        if isinstance(nested_data, (dict, list)):
            yield from _iter_paddle_lines_unsafe(nested_data)
            return
        texts = _as_sequence(pick_dict_value(result, "rec_texts", "texts", "rec_text"))
        scores = _as_sequence(pick_dict_value(result, "rec_scores", "scores", "rec_score"))
        boxes = _as_sequence(pick_dict_value(result, "rec_polys", "dt_polys", "boxes", "rec_boxes"))
        if not texts:
            return
        for index, text in enumerate(texts):
            normalized_text = clean_text(str(text))
            if not normalized_text:
                continue
            score = scores[index] if index < len(scores) else 1.0
            box = boxes[index] if index < len(boxes) else None
            yield OcrLine(
                text=normalized_text,
                confidence=normalize_confidence(score),
                box=normalize_box(box),
            )
        return
    if isinstance(result, list):
        if is_legacy_paddle_line(result):
            yield from _yield_legacy_paddle_line(result)
            return
        for item in result:
            yield from _iter_paddle_lines_unsafe(item)
        return
    if isinstance(result, tuple):
        if is_legacy_paddle_line(result):
            yield from _yield_legacy_paddle_line(result)
            return
        yield from _iter_paddle_lines_unsafe(list(result))


def _as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if hasattr(value, "tolist"):
        try:
            value = value.tolist()
        except Exception:
            return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _yield_legacy_paddle_line(result: Any):
    try:
        payload = result[1]
        text = clean_text(str(payload[0]))
        if not text:
            return
        confidence = normalize_confidence(payload[1] if len(payload) > 1 else 1.0)
        yield OcrLine(text=text, confidence=confidence, box=normalize_box(result[0]))
    except (IndexError, TypeError, KeyError, ValueError):
        return


def pick_dict_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def is_legacy_paddle_line(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    payload = value[1]
    return isinstance(payload, (list, tuple)) and len(payload) >= 1 and isinstance(payload[0], str)


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
        try:
            box = box.tolist()
        except Exception:
            return zero_box()
    points: list[list[float]] = []
    # Flat [x1,y1,x2,y2,...] boxes from some paddlex versions.
    if isinstance(box, (list, tuple)) and box and all(isinstance(item, (int, float)) for item in box):
        numbers = [float(item) for item in box]
        if len(numbers) >= 8:
            points = [
                [numbers[0], numbers[1]],
                [numbers[2], numbers[3]],
                [numbers[4], numbers[5]],
                [numbers[6], numbers[7]],
            ]
            return points
        if len(numbers) >= 4:
            x1, y1, x2, y2 = numbers[0], numbers[1], numbers[2], numbers[3]
            return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
    for point in box if isinstance(box, (list, tuple)) else []:
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
    if not lines:
        return ""
    rows = group_ocr_rows(lines)
    row_text = [" ".join(line.text for line in row if line.text).strip() for row in rows]
    return clean_text("\n".join(text for text in row_text if text))


def group_ocr_rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    if not lines:
        return []
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
    if not lines:
        return 12.0
    heights = [max(1.0, box_bottom(line.box) - box_top(line.box)) for line in lines]
    average_height = sum(heights) / len(heights) if heights else 12.0
    return max(8.0, average_height * 0.6)


def average_center_y(lines: list[OcrLine]) -> float:
    if not lines:
        return 0.0
    return sum(box_center_y(line.box) for line in lines) / len(lines)


def box_left(box: list[list[float]]) -> float:
    if not box:
        return 0.0
    return min(point[0] for point in box)


def box_top(box: list[list[float]]) -> float:
    if not box:
        return 0.0
    return min(point[1] for point in box)


def box_bottom(box: list[list[float]]) -> float:
    if not box:
        return 0.0
    return max(point[1] for point in box)


def box_center_y(box: list[list[float]]) -> float:
    return (box_top(box) + box_bottom(box)) / 2
