#!/usr/bin/env python3
"""Build a small Roku-friendly Internet Archive movie feed.

The public-domain status is an uploader-assigned metadata label, not a legal
verification. Only items with that label and a publicly listed MP4 are added.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "playlists" / "archive_movies.m3u8"
COVERS = ROOT / "covers" / "ia-movies"
RAW_COVERS = "https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/covers/ia-movies"
HEADERS = {"User-Agent": "JGJG-TV-Radio-Archive-Feed/1.0"}
QUERY = "mediatype:movies AND licenseurl:http*publicdomain*"


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()



def cache_cover(identifier: str, record: dict) -> str:
    """Cache the Internet Archive item thumbnail in this repository."""
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", identifier)
    names = []
    for file_info in record.get("files") or []:
        name = str(file_info.get("name") or "")
        if name.lower() in {"__ia_thumb.jpg", "cover.jpg", "poster.jpg", "thumbnail.jpg"}:
            names.append(name)
    names.sort(key=lambda name: 0 if name.lower() == "__ia_thumb.jpg" else 1)
    urls = [
        f"https://archive.org/download/{quote(identifier, safe='')}/{quote(name, safe='/')}"
        for name in names
    ]
    urls.append(f"https://archive.org/services/img/{quote(identifier, safe='')}")
    for url in urls:
        try:
            response = requests.get(url, headers=HEADERS, timeout=(15, 45))
            if response.status_code != 200 or len(response.content) < 1024:
                continue
            content_type = response.headers.get("content-type", "").lower()
            extension = ".jpg" if "image/jpeg" in content_type else ".png" if "image/png" in content_type else ""
            if not extension:
                continue
            COVERS.mkdir(parents=True, exist_ok=True)
            (COVERS / f"{safe_id}{extension}").write_bytes(response.content)
            return f"{RAW_COVERS}/{quote(safe_id + extension, safe='')}"
        except requests.RequestException as exc:
            logging.debug("Could not cache cover for %s: %s", identifier, exc)
    return f"https://archive.org/services/img/{quote(identifier, safe='')}"


def make_entry(doc: dict) -> tuple[str, str] | None:
    identifier = clean(doc.get("identifier"))
    license_url = clean(doc.get("licenseurl"))
    title = clean(doc.get("title"))
    try:
        year = int(clean(doc.get("year")))
    except (TypeError, ValueError):
        return None

    # Limit the first Roku catalog to vintage titles, avoiding mislabeled
    # recent user uploads and short-form template videos in Archive search.
    reject_title = re.compile(
        r"capcut|template|instagram|tiktok|download|transition|trend|"
        r"publicvideos|videoplay|online video cutter|full series|trailer|"
        r"miniaturas|song.?template",
        re.I,
    )
    if year < 1900 or year > 1969 or reject_title.search(title):
        return None
    if not identifier or "publicdomain" not in license_url.lower():
        return None

    time.sleep(0.15)
    response = requests.get(
        f"https://archive.org/metadata/{quote(identifier, safe='')}",
        headers=HEADERS,
        timeout=(15, 45),
    )
    response.raise_for_status()
    record = response.json()
    metadata = record.get("metadata") or {}
    confirmed_license = clean(metadata.get("licenseurl") or license_url)
    if "publicdomain" not in confirmed_license.lower():
        return None

    choices = []
    for file_info in record.get("files") or []:
        name = str(file_info.get("name") or "")
        if not name.lower().endswith(".mp4"):
            continue
        if str(file_info.get("private", "")).lower() in {"true", "1"}:
            continue
        try:
            size = int(file_info.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > 1_500_000_000:
            continue
        low = name.lower()
        score = (30 if ("512kb" in low or "256kb" in low) else 0)
        score += 20 if ("h264" in low or "h.264" in low) else 0
        score += 10 if size else 0
        choices.append((score, name))
    if not choices:
        return None

    filename = sorted(choices, reverse=True)[0][1]
    title = title or identifier
    year = str(year)
    if year not in title:
        title = f"{title} ({year})"
    logo = cache_cover(identifier, record)
    stream = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(filename, safe='/')}"
    extinf = (
        f'#EXTINF:-1 tvg-id="ia-{identifier}" tvg-logo="{logo}" '
        f'group-title="Internet Archive - Public Domain label",{title}'
    )
    return extinf, stream


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    queries = [
        QUERY,
        # Mirrors the user's Archive movies collection search for "films".
        "collection:movies AND mediatype:movies AND films AND licenseurl:http*publicdomain*",
    ]
    docs_by_id = {}
    for query in queries:
        params = [
            ("q", query),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("fl[]", "year"),
            ("fl[]", "licenseurl"),
            ("sort[]", "downloads desc"),
            ("rows", "100"),
            ("page", "1"),
            ("output", "json"),
        ]
        response = requests.get(
            "https://archive.org/advancedsearch.php",
            params=params,
            headers=HEADERS,
            timeout=(15, 45),
        )
        response.raise_for_status()
        for doc in (response.json().get("response") or {}).get("docs") or []:
            identifier = clean(doc.get("identifier"))
            if identifier:
                docs_by_id.setdefault(identifier, doc)
    docs = list(docs_by_id.values())
    logging.info("Archive searches returned %d unique candidates", len(docs))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        future_docs = {pool.submit(make_entry, doc): doc for doc in docs}
        for future in concurrent.futures.as_completed(future_docs):
            try:
                item = future.result()
                if item:
                    identifier = clean(future_docs[future].get("identifier"))
                    results[identifier] = item
            except Exception as exc:
                logging.warning("Skipping an Archive item: %s", exc)

    lines = ["#EXTM3U"]
    for doc in docs:
        item = results.get(clean(doc.get("identifier")))
        if item:
            lines.extend(item)
    if len(lines) < 41:
        logging.error("Only %d playable labeled items; leaving existing feed untouched", (len(lines) - 1) // 2)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("Wrote %d public-domain-label items to %s", (len(lines) - 1) // 2, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
