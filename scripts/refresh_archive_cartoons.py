#!/usr/bin/env python3
"""Refresh an Internet Archive cartoon review catalogue and approved Roku feed.

Search results are candidates only. Roku playback is generated solely for item
identifiers listed in playlists/archive_cartoons_approved.txt after review.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "playlists" / "archive_cartoons_review.json"
APPROVED = ROOT / "playlists" / "archive_cartoons_approved.txt"
OUTPUT = ROOT / "playlists" / "archive_cartoons.m3u8"
PREVIEW = ROOT / "playlists" / "archive_cartoons_review.m3u8"
HEADERS = {"User-Agent": "JGJG-TV-Radio-IA-Cartoons/1.0"}
QUERY = (
    "mediatype:movies AND (subject:cartoon OR subject:animation "
    "OR title:cartoon OR title:animation)"
)
MAX_CANDIDATES = 1000
MAX_PREVIEW_ITEMS = 120


def clean(value: object, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()
    return text[:limit]


def fetch_candidates() -> list[dict]:
    params = [
        ("q", QUERY),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "year"),
        ("fl[]", "creator"),
        ("fl[]", "licenseurl"),
        ("fl[]", "description"),
        ("fl[]", "subject"),
        ("sort[]", "downloads desc"),
        ("rows", str(MAX_CANDIDATES)),
        ("page", "1"),
        ("output", "json"),
    ]
    response = requests.get(
        "https://archive.org/advancedsearch.php",
        params=params,
        headers=HEADERS,
        timeout=(15, 60),
    )
    response.raise_for_status()
    raw = (response.json().get("response") or {}).get("docs") or []
    results = []
    for doc in raw:
        identifier = clean(doc.get("identifier"), 160)
        if not identifier:
            continue
        results.append(
            {
                "identifier": identifier,
                "title": clean(doc.get("title"), 250) or identifier,
                "year": clean(doc.get("year"), 16),
                "creator": clean(doc.get("creator"), 250),
                "license_url": clean(doc.get("licenseurl"), 300),
                "description": clean(doc.get("description"), 500),
                "subjects": doc.get("subject") or [],
                "item_url": f"https://archive.org/details/{quote(identifier, safe='')}",
                "thumbnail_url": f"https://archive.org/services/img/{quote(identifier, safe='')}",
                "review_status": "needs-review",
            }
        )
    return results


def approved_identifiers() -> list[str]:
    identifiers = []
    for line in APPROVED.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if value and value not in identifiers:
            identifiers.append(value)
    return identifiers


def playable_entry(identifier: str, preview: bool = False) -> tuple[str, str] | None:
    response = requests.get(
        f"https://archive.org/metadata/{quote(identifier, safe='')}",
        headers=HEADERS,
        timeout=(15, 60),
    )
    response.raise_for_status()
    record = response.json()
    metadata = record.get("metadata") or {}
    media_type = clean(metadata.get("mediatype"), 40).lower()
    if media_type != "movies":
        logging.warning("Skipping %s: not an Archive movie item", identifier)
        return None

    license_url = clean(metadata.get("licenseurl"), 300)
    license_lower = license_url.lower()
    if not ("publicdomain" in license_lower or "creativecommons.org/licenses/" in license_lower):
        logging.warning("Skipping %s: no recognized rights URL in item metadata", identifier)
        return None

    options = []
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
        if size and size > 1_500_000_000:
            continue
        lower_name = name.lower()
        score = 20 if "512kb" in lower_name else 0
        score += 15 if "h264" in lower_name or "h.264" in lower_name else 0
        score += 5 if size else 0
        options.append((score, name))
    if not options:
        logging.warning("Skipping %s: no public MP4 file found", identifier)
        return None

    title = clean(metadata.get("title"), 250) or identifier
    filename = sorted(options, reverse=True)[0][1]
    logo = f"https://archive.org/services/img/{quote(identifier, safe='')}"
    stream = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(filename, safe='/')}"
    if preview:
        label = "PREVIEW ONLY - title and rights unverified"
        title = "REVIEW - " + title
    else:
        label = f"Internet Archive | {license_url}"
    extinf = f'#EXTINF:-1 tvg-id="ia-cartoon-{identifier}" tvg-logo="{logo}" group-title="{label}",{title}'
    return extinf, stream


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    candidates = fetch_candidates()
    CANDIDATES.write_text(
        json.dumps({"source": "Internet Archive Advanced Search", "query": QUERY, "items": candidates}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    logging.info("Wrote %d cartoon candidates for review", len(candidates))

    approved = approved_identifiers()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(playable_entry, approved))
    lines = ["#EXTM3U"]
    for entry in results:
        if entry:
            lines.extend(entry)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("Wrote %d rights-reviewed Roku entries", (len(lines) - 1) // 2)

    preview_ids = []
    for item in candidates:
        license_url = clean(item.get("license_url")).lower()
        has_license_label = "publicdomain" in license_url or "creativecommons.org/licenses/" in license_url
        identifier = clean(item.get("identifier"), 160)
        if has_license_label and identifier and identifier not in preview_ids:
            preview_ids.append(identifier)
        if len(preview_ids) >= MAX_PREVIEW_ITEMS:
            break
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        preview_results = list(pool.map(lambda item_id: playable_entry(item_id, True), preview_ids))
    preview_lines = ["#EXTM3U"]
    for entry in preview_results:
        if entry:
            preview_lines.extend(entry)
    PREVIEW.write_text("\n".join(preview_lines) + "\n", encoding="utf-8")
    logging.info("Wrote %d unverified review-preview entries", (len(preview_lines) - 1) // 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
