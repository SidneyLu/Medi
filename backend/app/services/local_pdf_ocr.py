from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import fitz


MODEL_NAME = "paddleocr-local"
EDGE_SPACE_CHARS = " \t\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u200b\u202f\u205f\u3000\ufeff"
CJK_INNER_SPACE_PATTERN = re.compile(r"(?<=[\u4e00-\u9fff])[ \t\u00a0\u1680\u2000-\u200b\u202f\u205f\u3000\ufeff]+(?=[\u4e00-\u9fff])")


@dataclass(frozen=True)
class LocalOcrLine:
    text: str
    confidence: float
    box: list[list[float]]


@dataclass(frozen=True)
class LocalPageResult:
    record: dict[str, Any] | None
    raw_record: dict[str, Any] | None
    error: dict[str, Any] | None
    seconds: float


class LocalPdfOcrProcessor:
    def __init__(
        self,
        *,
        render_scale: float = 2.0,
        max_image_size: int = 2400,
        min_confidence: float = 0.5,
        device: str = "cpu",
    ) -> None:
        self.render_scale = render_scale
        self.max_image_size = max_image_size
        self.min_confidence = min_confidence
        self.device = device
        self._ocr: Any | None = None

    def process_page(self, pdf_path: str | Path, *, document_id: str, pdf_page: int, image_dir: str | Path) -> LocalPageResult:
        import time

        started = time.perf_counter()
        processed_at = utc_now()
        source_file = str(Path(pdf_path).expanduser().resolve())
        raw_record: dict[str, Any] | None = None
        try:
            image_path, image_width, image_height = render_page_to_jpeg(
                pdf_path,
                pdf_page,
                image_dir=image_dir,
                render_scale=self.render_scale,
                max_image_size=self.max_image_size,
            )
            try:
                ocr_lines = self.extract_lines(image_path)
            finally:
                try:
                    image_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raw_record = build_raw_record(
                document_id=document_id,
                pdf_page=pdf_page,
                processed_at=processed_at,
                image_width=image_width,
                image_height=image_height,
                ocr_lines=ocr_lines,
            )
            record = build_clean_record(
                raw_record,
                source_file=source_file,
                processed_at=processed_at,
            )
            return LocalPageResult(record=record, raw_record=raw_record, error=None, seconds=time.perf_counter() - started)
        except Exception as exc:
            error = {
                "document_id": document_id,
                "source_file": source_file,
                "pdf_page": pdf_page,
                "error": str(exc),
                "processed_at": processed_at,
                "model_name": MODEL_NAME,
            }
            return LocalPageResult(record=None, raw_record=raw_record, error=error, seconds=time.perf_counter() - started)

    def extract_lines(self, image_path: str | Path) -> list[LocalOcrLine]:
        ocr = self._engine()
        if hasattr(ocr, "predict"):
            result = ocr.predict(str(image_path))
        else:
            result = ocr.ocr(str(image_path), cls=True)
        lines = []
        for line in iter_ocr_lines(result):
            text = clean_text(line.text)
            if not text or line.confidence < self.min_confidence:
                continue
            lines.append(LocalOcrLine(text=text, confidence=line.confidence, box=line.box))
        return lines

    def _engine(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("PaddleOCR is not installed. Install paddleocr before running local OCR.") from exc
        use_gpu = self.device.lower() in {"gpu", "cuda"}
        try:
            self._ocr = PaddleOCR(lang="ch", use_textline_orientation=True, device="gpu:0" if use_gpu else "cpu")
        except TypeError:
            self._ocr = PaddleOCR(lang="ch", use_angle_cls=True, use_gpu=use_gpu)
        return self._ocr


def render_page_to_jpeg(
    pdf_path: str | Path,
    pdf_page: int,
    *,
    image_dir: str | Path,
    render_scale: float = 2.0,
    max_image_size: int = 2400,
) -> tuple[Path, int, int]:
    if pdf_page < 1:
        raise ValueError("pdf_page is 1-based and must be greater than zero")
    pdf = Path(pdf_path).expanduser().resolve()
    target_dir = Path(image_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    image_path = target_dir / f"page_{pdf_page:04d}.jpg"
    with fitz.open(pdf) as document:
        if pdf_page > document.page_count:
            raise ValueError(f"pdf_page {pdf_page} exceeds PDF page count {document.page_count}")
        page = document.load_page(pdf_page - 1)
        width = page.rect.width * render_scale
        height = page.rect.height * render_scale
        longest = max(width, height)
        scale = render_scale if longest <= max_image_size else render_scale * (max_image_size / longest)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        pixmap.save(image_path)
        return image_path, pixmap.width, pixmap.height


def iter_ocr_lines(result: Any) -> Iterable[LocalOcrLine]:
    if hasattr(result, "json"):
        json_value = result.json
        if callable(json_value):
            json_value = json_value()
        if isinstance(json_value, dict):
            yield from iter_ocr_lines(json_value)
            return
    if isinstance(result, list):
        if is_legacy_line(result):
            yield LocalOcrLine(text=str(result[1][0]), confidence=float(result[1][1]), box=normalize_box(result[0]))
            return
        for item in result:
            yield from iter_ocr_lines(item)
        return
    if isinstance(result, dict):
        nested_result = result.get("res")
        if isinstance(nested_result, dict):
            yield from iter_ocr_lines(nested_result)
            return
        texts = pick_dict_value(result, "rec_texts", "texts")
        scores = pick_dict_value(result, "rec_scores", "scores")
        boxes = pick_dict_value(result, "rec_polys", "dt_polys", "boxes")
        texts = [] if texts is None else texts
        scores = [] if scores is None else scores
        boxes = [] if boxes is None else boxes
        for text, score, box in zip(texts, scores, boxes):
            yield LocalOcrLine(text=str(text), confidence=float(score), box=normalize_box(box))
        return
    if isinstance(result, tuple) and len(result) >= 2:
        if is_legacy_line(result):
            yield LocalOcrLine(text=str(result[1][0]), confidence=float(result[1][1]), box=normalize_box(result[0]))
            return
        box = normalize_box(result[0])
        payload = result[1]
        if isinstance(payload, (tuple, list)) and len(payload) >= 2:
            yield LocalOcrLine(text=str(payload[0]), confidence=float(payload[1]), box=box)


def pick_dict_value(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def is_legacy_line(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    payload = value[1]
    return isinstance(payload, (list, tuple)) and len(payload) >= 2 and isinstance(payload[0], str)


def build_raw_record(
    *,
    document_id: str,
    pdf_page: int,
    processed_at: str,
    image_width: int,
    image_height: int,
    ocr_lines: list[LocalOcrLine],
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "pdf_page": pdf_page,
        "model_name": MODEL_NAME,
        "processed_at": processed_at,
        "image_width": image_width,
        "image_height": image_height,
        "ocr_lines": [
            {"text": line.text, "confidence": line.confidence, "box": line.box}
            for line in ocr_lines
        ],
    }


def build_clean_record(raw_record: dict[str, Any], *, source_file: str, processed_at: str) -> dict[str, Any]:
    lines = [
        LocalOcrLine(
            text=clean_text(str(item.get("text") or "")),
            confidence=float(item.get("confidence") or 0.0),
            box=normalize_box(item.get("box") or []),
        )
        for item in raw_record.get("ocr_lines", [])
        if isinstance(item, dict)
    ]
    ordered = order_lines(lines, image_width=int(raw_record.get("image_width") or 0), image_height=int(raw_record.get("image_height") or 0))
    body_lines = [line.text for line in ordered if is_effective_text_line(line.text)]
    body_text = clean_body_text("\n".join(body_lines))
    title = pick_title(body_text.splitlines())
    search_text = build_search_text(title, body_text)
    searchable = bool(search_text)
    content_hash = hashlib.sha256(search_text.encode("utf-8")).hexdigest() if search_text else ""
    pdf_page = int(raw_record["pdf_page"])
    page_type = "content" if searchable else "blank"
    return {
        "document_id": str(raw_record["document_id"]),
        "source_file": source_file,
        "pdf_page": pdf_page,
        "printed_page": printed_page_from_offset(pdf_page),
        "page_type": page_type,
        "title": title,
        "body_text": body_text,
        "table_text": "",
        "figure_text": "",
        "medical_terms": [],
        "searchable": searchable,
        "skip_reason": None if searchable else "blank page",
        "search_text": search_text,
        "content_hash": content_hash,
        "processed_at": processed_at,
        "model_name": MODEL_NAME,
    }


def order_lines(lines: list[LocalOcrLine], *, image_width: int, image_height: int) -> list[LocalOcrLine]:
    if not lines:
        return []
    if not image_width:
        return sorted(lines, key=lambda line: (box_top(line.box), box_left(line.box)))
    midpoint = image_width / 2
    spanning = [line for line in lines if is_spanning_line(line, image_width)]
    normal = [line for line in lines if line not in spanning]
    left = [line for line in normal if box_center_x(line.box) <= midpoint]
    right = [line for line in normal if box_center_x(line.box) > midpoint]
    if not is_reliable_two_column(left, right, image_width):
        return sorted(lines, key=lambda line: (box_top(line.box), box_left(line.box)))
    first_column_top = min([box_top(line.box) for line in normal], default=image_height or 0)
    top_spanning = [line for line in spanning if box_top(line.box) <= first_column_top + max(20, image_height * 0.03)]
    used_ids = set_by_identity(top_spanning + left + right)
    remaining = [line for line in lines if id(line) not in used_ids]
    return (
        sorted(top_spanning, key=lambda line: (box_top(line.box), box_left(line.box)))
        + sorted(left, key=lambda line: (box_top(line.box), box_left(line.box)))
        + sorted(right, key=lambda line: (box_top(line.box), box_left(line.box)))
        + sorted(remaining, key=lambda line: (box_top(line.box), box_left(line.box)))
    )


def is_reliable_two_column(left: list[LocalOcrLine], right: list[LocalOcrLine], image_width: int) -> bool:
    if len(left) < 4 or len(right) < 4:
        return False
    left_right_edge = max(box_right(line.box) for line in left)
    right_left_edge = min(box_left(line.box) for line in right)
    return right_left_edge - left_right_edge > image_width * 0.03


def is_spanning_line(line: LocalOcrLine, image_width: int) -> bool:
    left = box_left(line.box)
    right = box_right(line.box)
    width = max(0.0, right - left)
    midpoint = image_width / 2
    return left < midpoint < right and width >= image_width * 0.45


def set_by_identity(lines: list[LocalOcrLine]) -> set[int]:
    return {id(line) for line in lines}


def normalize_box(box: Any) -> list[list[float]]:
    if box is None:
        return zero_box()
    points = []
    if hasattr(box, "tolist"):
        box = box.tolist()
    for point in box:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append([float(point[0]), float(point[1])])
    if len(points) >= 4:
        return points[:4]
    return zero_box()


def zero_box() -> list[list[float]]:
    return [[0.0, 0.0], [0.0, 0.0], [0.0, 0.0], [0.0, 0.0]]


def box_left(box: list[list[float]]) -> float:
    return min(point[0] for point in box)


def box_right(box: list[list[float]]) -> float:
    return max(point[0] for point in box)


def box_top(box: list[list[float]]) -> float:
    return min(point[1] for point in box)


def box_center_x(box: list[list[float]]) -> float:
    return (box_left(box) + box_right(box)) / 2


def clean_body_text(text: str) -> str:
    lines = [clean_text(line) for line in text.replace("\r", "\n").split("\n")]
    kept = []
    previous = ""
    for line in lines:
        if not is_effective_text_line(line):
            continue
        if line == previous:
            continue
        kept.append(line)
        previous = line
    return "\n".join(kept).strip()


def clean_text(text: str) -> str:
    text = CJK_INNER_SPACE_PATTERN.sub("", text)
    text = re.sub(r"[ \t\u00a0\u1680\u2000-\u200b\u202f\u205f\u3000\ufeff]+", " ", text)
    return text.strip(EDGE_SPACE_CHARS)


def is_effective_text_line(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"[-–—]?\s*\d+\s*[-–—]?", text):
        return False
    return True


def pick_title(lines: list[str]) -> str:
    for line in lines:
        text = clean_text(line)
        if 2 <= len(text) <= 40 and not re.fullmatch(r"\d+", text) and is_effective_text_line(text):
            return text
    return ""


def build_search_text(title: str, body_text: str) -> str:
    body_for_search = remove_first_line_if_same(body_text, title)
    return "\n".join(part for part in [title, body_for_search] if part).strip()


def remove_first_line_if_same(text: str, title: str) -> str:
    if not text or not title:
        return text
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip(EDGE_SPACE_CHARS):
            continue
        if line.strip(EDGE_SPACE_CHARS) != title:
            return text
        return "\n".join(lines[:index] + lines[index + 1 :]).strip("\n")
    return text


def printed_page_from_offset(pdf_page: int) -> str | None:
    raw_offset = os.getenv("PDF_PAGE_OFFSET")
    if raw_offset is None:
        return None
    offset = int(raw_offset)
    printed_page = pdf_page - offset
    return str(printed_page) if printed_page >= 1 else None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f"{target.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
        file.flush()
    temp_path.replace(target)
