#!/usr/bin/env python3
"""Build a Roku-compatible Internet Archive music playlist.

The feed includes audio items whose Archive metadata contains an uploader-provided
Public Domain or Creative Commons license URL. Archive labels are not independently verified.
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
OUTPUT = ROOT / "playlists" / "archive_music.m3u8"
HEADERS = {"User-Agent": "JGJG-TV-Radio-IA-Music/1.0"}
QUERY = 'mediatype:audio AND (subject:music OR title:music OR subject:instrumental)'
MAX_CANDIDATES = 500
MAX_TRACKS = 150
MAX_FILE_SIZE = 500_000_000


def clean(value: object, limit: int = 300) -> str:
    return re.sub(r"\\s+", " ", str(value or "")).replace('"', "'").strip()[:limit]


def has_open_license(value: object) -> bool:
    license_url = clean(value, 500).lower()
    return "publicdomain" in license_url or "creativecommons.org/licenses/" in license_url


def fetch_candidates() -> list[dict]:
    params = [
        ("q", QUERY),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "creator"),
        ("fl[]", "licenseurl"),
        ("sort[]", "downloads desc"),
        ("rows", str(MAX_CANDIDATES)),
        ("page", "1"),
        ("output", "json"),
    ]
    response = requests.get("https://archive.org/advancedsearch.php", params=params, headers=HEADERS, timeout=(15, 60))
    response.raise_for_status()
    docs = (response.json().get("response") or {}).get("docs") or []
    return [doc for doc in docs if clean(doc.get("identifier")) and has_open_license(doc.get("licenseurl"))]


def playable_entry(doc: dict) -> tuple[str, str] | None:
    identifier = clean(doc.get("identifier"), 160)
    try:
        response = requests.get(f"https://archive.org/metadata/{quote(identifier, safe='')}", headers=HEADERS, timeout=(15, 45))
        response.raise_for_status()
        record = response.json()
    except (requests.RequestException, ValueError) as exc:
        logging.info("Skipping %s: metadata unavailable (%s)", identifier, exc)
        return None

    metadata = record.get("metadata") or {}
    if clean(metadata.get("mediatype"), 40).lower() != "audio" or not has_open_license(metadata.get("licenseurl")):
        return None

    options = []
    for file_info in record.get("files") or []:
        name = str(file_info.get("name") or "")
        lower = name.lower()
        if not lower.endswith((".mp3", ".flac", ".m4a", ".aac")):
            continue
        if str(file_info.get("private", "")).lower() in {"true", "1"}:
            continue
        try:
            size = int(file_info.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > MAX_FILE_SIZE:
            continue
        score = 0
        score += 40 if lower.endswith(".mp3") else 0
        score += 30 if lower.endswith(".m4a") else 0
        score += 20 if lower.endswith(".flac") else 0
        score += 10 if size else 0
        options.append((score, name))
    if not options:
        return None

    filename = sorted(options, reverse=True)[0][1]
    title = clean(metadata.get("title") or doc.get("title") or identifier)
    creator = clean(metadata.get("creator") or doc.get("creator") or "Unknown artist", 160)
    license_url = clean(metadata.get("licenseurl") or doc.get("licenseurl"), 300)
    logo = f"https://archive.org/services/img/{quote(identifier, safe='')}"
    stream = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(filename, safe='/')}"
    label = f"Internet Archive | {creator} | {license_url}"
    return f'#EXTINF:-1 tvg-id="ia-music-{identifier}" tvg-logo="{logo}" group-title="{label}",{title}', stream


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    candidates = fetch_candidates()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        entries = list(pool.map(playable_entry, candidates))
    lines = ["#EXTM3U"]
    for entry in entries:
        if entry:
            lines.extend(entry)
            if (len(lines) - 1) // 2 >= MAX_TRACKS:
                break
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logging.info("Wrote %d audio entries", (len(lines) - 1) // 2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
