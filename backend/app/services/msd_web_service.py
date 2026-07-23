"""MSD manuals.cn site search + page extract for citation enrichment only."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.responses import AppError

USER_AGENT = "MediCitationBot/1.0 (+local; citation-enrichment)"
SEARCH_PATH = "/api/search/search"
DEFAULT_TIMEOUT_SECONDS = 20.0
MAX_SNIPPET_CHARS = 500
MAX_SUMMARY_CHARS = 2000
MAX_HTML_CHARS = 600_000

BLOCKED_PATH_PREFIXES = (
    "/home/searchresults",
    "/home/resourcespages",
    "/home/content",
    "/home/errorpages",
    "/home/_next",
)

_WS_RE = re.compile(r"\s+")


class MsdWebService:
    def web_search(self, q: str, limit: int = 5) -> list[dict[str, str]]:
        query = (q or "").strip()
        if not query:
            raise AppError(status_code=422, code=42201, message="q must not be empty", error_type="validation_error")
        if limit < 1 or limit > 20:
            raise AppError(status_code=422, code=42202, message="limit must be between 1 and 20", error_type="validation_error")

        settings = get_settings()
        origin = self._site_origin(settings.msd_source_base_url)
        # Over-fetch so homepage / blocked / duplicate paths can be filtered.
        rows = min(max(limit * 3, limit), 30)
        params = {
            "q": query,
            "rows": str(rows),
            "start": "0",
            "model": "Default",
            "language": "zh",
        }
        try:
            with httpx.Client(
                timeout=DEFAULT_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(f"{origin}{SEARCH_PATH}", params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.TimeoutException as exc:
            raise AppError(status_code=504, code=50401, message="MSD search timed out", error_type="request_failed") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(status_code=502, code=50201, message="MSD search request failed", error_type="request_failed") from exc

        if not isinstance(payload, dict) or payload.get("status") != 200:
            raise AppError(status_code=502, code=50202, message="MSD search returned unexpected status", error_type="request_failed")

        docs = ((payload.get("data") or {}).get("response") or {}).get("docs") or []
        if not isinstance(docs, list):
            return []

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for doc in docs:
            if not isinstance(doc, dict):
                continue
            item = self._doc_to_result(doc, origin)
            if item is None or item["url"] in seen:
                continue
            seen.add(item["url"])
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def web_extractor(self, url: str) -> dict[str, str]:
        settings = get_settings()
        origin = self._site_origin(settings.msd_source_base_url)
        canonical = self.normalize_topic_url(url, origin)
        if canonical is None:
            raise AppError(
                status_code=422,
                code=42203,
                message="url must be an msdmanuals.cn topic page under /home/",
                error_type="validation_error",
            )

        try:
            with httpx.Client(
                timeout=DEFAULT_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = client.get(canonical)
                response.raise_for_status()
                html = response.text[:MAX_HTML_CHARS]
                final_url = str(response.url)
        except httpx.TimeoutException as exc:
            raise AppError(status_code=504, code=50402, message="MSD page fetch timed out", error_type="request_failed") from exc
        except httpx.HTTPError as exc:
            raise AppError(status_code=502, code=50203, message="MSD page fetch failed", error_type="request_failed") from exc

        final_canonical = self.normalize_topic_url(final_url, origin) or canonical
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        h1 = soup.select_one("#topicHeaderTitle") or soup.find("h1")
        if h1 is not None:
            title = _clean_text(h1.get_text(" ", strip=True))
        if not title:
            og = soup.select_one('meta[property="og:title"]')
            if og and og.get("content"):
                title = _clean_text(str(og["content"]))
        if not title and soup.title and soup.title.string:
            title = _clean_text(str(soup.title.string).split(" - ")[0])
        title = re.sub(r"\s*[-|].*默沙东.*$", "", title).strip()

        summary_parts: list[str] = []
        meta_desc = soup.select_one('meta[name="description"]') or soup.select_one('meta[property="og:description"]')
        if meta_desc and meta_desc.get("content"):
            summary_parts.append(_clean_text(str(meta_desc["content"])))

        if not summary_parts or sum(len(p) for p in summary_parts) < 40:
            for selector in ("main", "article", "[class*='TopicBody']", "body"):
                container = soup.select_one(selector)
                if container is None:
                    continue
                for node in container.find_all(["p", "li"]):
                    text = _clean_text(node.get_text(" ", strip=True))
                    if len(text) < 20:
                        continue
                    summary_parts.append(text)
                    if sum(len(part) for part in summary_parts) >= MAX_SUMMARY_CHARS:
                        break
                if summary_parts:
                    break

        summary = _truncate(" ".join(summary_parts), MAX_SUMMARY_CHARS)
        if not title:
            raise AppError(status_code=502, code=50204, message="MSD page title could not be extracted", error_type="request_failed")

        return {"title": title, "url": final_canonical, "summary": summary}

    def normalize_topic_url(self, url: str | None, site_origin: str | None = None) -> str | None:
        if site_origin is None:
            site_origin = self._site_origin(get_settings().msd_source_base_url)
        return self._canonicalize_topic_url(url or "", site_origin)

    @staticmethod
    def _site_origin(base_url: str) -> str:
        parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
        scheme = parsed.scheme or "https"
        netloc = parsed.netloc or "www.msdmanuals.cn"
        return f"{scheme}://{netloc}".rstrip("/")

    def _doc_to_result(self, doc: dict, site_origin: str) -> dict[str, str] | None:
        title = _clean_text(
            str(
                doc.get("titlecomputed_t")
                or doc.get("title_t")
                or doc.get("optimizedtitle_t")
                or doc.get("_displayname")
                or ""
            )
        )
        relative = str(doc.get("relativeurlcomputed_s") or doc.get("uri_t") or "").strip()
        page_url = self._canonicalize_topic_url(relative, site_origin)
        if page_url is None:
            return None
        if not title:
            title = page_url.rsplit("/", 1)[-1].replace("-", " ")

        snippet_raw = (
            doc.get("summarycomputed_t")
            or doc.get("summary_t")
            or doc.get("descriptioncomputed_t")
            or doc.get("description_t")
            or ""
        )
        snippet = _truncate(_strip_html(str(snippet_raw)), MAX_SNIPPET_CHARS)
        return {"title": title, "url": page_url, "snippet": snippet}

    def _canonicalize_topic_url(self, value: str, site_origin: str) -> str | None:
        raw = (value or "").strip()
        if not raw:
            return None
        if raw.startswith("~/"):
            raw = raw[1:]
        if raw.startswith("/"):
            absolute = urljoin(f"{site_origin}/", raw.lstrip("/"))
        elif not raw.startswith(("http://", "https://")):
            absolute = urljoin(f"{site_origin}/", raw)
        else:
            absolute = raw

        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"}:
            return None
        host = (parsed.netloc or "").lower()
        if host not in {"www.msdmanuals.cn", "msdmanuals.cn"}:
            return None

        path = re.sub(r"/+", "/", parsed.path or "")
        path = path.rstrip("/") or "/"
        lower = path.lower()
        if lower in {"/home", "/"}:
            return None
        if not lower.startswith("/home/"):
            return None
        if any(lower.startswith(prefix) for prefix in BLOCKED_PATH_PREFIXES):
            return None
        # Require topic depth: /home/<section>/<topic>[/...]
        parts = [p for p in path.split("/") if p]
        if len(parts) < 3:
            return None
        return urlunparse(("https", "www.msdmanuals.cn", path, "", "", ""))


def _strip_html(value: str) -> str:
    if not value:
        return ""
    if "<" in value and ">" in value:
        text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    else:
        text = re.sub(r"<[^>]+>", " ", value)
    return _clean_text(unescape(text))


def _clean_text(value: str) -> str:
    return _WS_RE.sub(" ", (value or "").strip())


def _truncate(value: str, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
