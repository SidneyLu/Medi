"""Pre-download / warm up PaddleOCR models into the local cache.

Run once after installing paddleocr (with network), then later uploads
can reuse the files under the cache directory without re-downloading.

Usage (from backend/, medi conda env):

    python scripts/warmup_paddle_ocr.py

Optional: put models inside the project instead of ~/.paddlex

    set PADDLE_PDX_CACHE_HOME=%CD%\\storage\\paddle_models
    python scripts/warmup_paddle_ocr.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main() -> int:
    cache_home = os.environ.get("PADDLE_PDX_CACHE_HOME")
    if cache_home:
        print(f"Using PADDLE_PDX_CACHE_HOME={cache_home}")
    else:
        default_cache = Path.home() / ".paddlex"
        print(f"Using default cache: {default_cache}")

    print("Loading PaddleOCR (may download models on first run)...")
    started = time.perf_counter()
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("paddleocr is not installed. Activate medi env and install dependencies first.", file=sys.stderr)
        return 1

    try:
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
    except Exception as exc:
        print(f"Failed to initialize PaddleOCR: {exc}", file=sys.stderr)
        return 1

    elapsed = time.perf_counter() - started
    print(f"PaddleOCR ready in {elapsed:.1f}s")
    print("Models are cached locally. Keep this cache when packaging the environment.")
    print("Restart the Medi backend so it can reuse the shared OCR engine.")
    _ = engine
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
