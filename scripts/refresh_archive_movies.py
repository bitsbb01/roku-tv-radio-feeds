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
HEADERS = {"User-Agent": "JGJG-TV-Radio-Archive-Feed/1.0"}
QUERY = "mediatype:movies AND licenseurl:http*publicdomain*"


def clean(value: object) -> str:
    return re.sub(r"\\s+", " ", str(value or "")).replace('"', "'").strip()


def make_entry(doc: dict) -> tuple[str, str] | None:
    identifier = clean(doc.get("identifier"))
    license_url = clean(doc.get("licenseurl"))
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
    title = clean(doc.get("title")) or identifier
    year = clean(doc.get("year"))
    if year and year not in title:
        title = f"{title} ({year})"
    logo = f"https://archive.org/services/img/{quote(identifier, safe='')}"
    stream = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(filename, safe='/')}"
    extinf = (
        f'#EXTINF:-1 tvg-id="ia-{identifier}" tvg-logo="{logo}" '
        f'group-title="Internet Archive - Public Domain label",{title}'
    )
    return extinf, stream


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    params = [
        ("q", QUERY),
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
    docs = (response.json().get("response") or {}).get("docs") or []
    logging.info("Archive search returned %d candidates", len(docs))

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

    ordered = []
    for doc in docs:
        item = results.get(clean(doc.get("identifier")))
        if item:
            ordered.extend(item)
    if len(ordered) < 20:
        logging.error("Only %d playable labeled items; leaving existing feed untouched", len(ordered) // 2)
        return 1

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for index in range(0, len(ordered), 2):
        lines.extend((ordered[index], ordered[index + 1]))
    OUTPUT.write_text("\\n".join(lines) + "\\n", encoding="utf-8")
    logging.info("Wrote %d public-domain-label items to %s", len(ordered) // 2, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
