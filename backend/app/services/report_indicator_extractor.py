from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

from app.models.schemas import ReportItem


RANGE_PATTERN = re.compile(
    r"(?P<low>[<>]?\d+(?:\.\d+)?)\s*(?:-|~|－|–|—|至|到)\s*(?P<high>[<>]?\d+(?:\.\d+)?)"
)
NUMBER_PATTERN = re.compile(r"(?P<flag>[<>])?(?P<value>\d+(?:\.\d+)?)")
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
    def extract(self, file_path: Path, content: bytes) -> tuple[str, list[ReportItem], str | None]:
        suffix = file_path.suffix.lower()
        error_message: str | None = None
        if suffix == ".pdf":
            try:
                raw_text = self._extract_pdf_text(content)
            except Exception as exc:
                raw_text = ""
                error_message = f"PDF text extraction failed: {exc}"
            if not raw_text.strip() and error_message is None:
                error_message = "PDF text layer is empty; image-only report OCR is not available in this runtime."
        elif suffix in {".jpg", ".jpeg", ".png"}:
            raw_text, error_message = self._extract_image_text(file_path)
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
            from paddleocr import PaddleOCR
        except ImportError:
            return "", "Image report OCR requires paddleocr; upload a text-based PDF or install paddleocr."
        try:
            ocr = PaddleOCR(lang="ch", use_angle_cls=True, use_gpu=False)
            result = ocr.ocr(str(file_path), cls=True)
            lines = [line for line in _iter_paddle_lines(result) if line]
            return clean_text("\n".join(lines)), None
        except Exception as exc:
            return "", f"Image OCR failed: {exc}"

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


def _iter_paddle_lines(result: Any):
    if isinstance(result, list):
        if len(result) == 2 and isinstance(result[1], (list, tuple)) and result[1] and isinstance(result[1][0], str):
            yield str(result[1][0])
            return
        for item in result:
            yield from _iter_paddle_lines(item)
    elif isinstance(result, tuple):
        yield from _iter_paddle_lines(list(result))
