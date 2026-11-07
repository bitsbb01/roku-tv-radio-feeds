#!/usr/bin/env python3
"""Build country M3U feeds from IPTV Cat's paginated public listings."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "playlists"
MAX_PAGES = 100
MAX_WORKERS = 3
MIN_ENTRIES = {"usa": 400, "canada": 100, "uk": 100}
COUNTRIES = {
    "usa": {
        "name": "United States",
        "code": "US",
        "url": "https://iptvcat.com/united_states_of_america__11",
    },
    "canada": {
        "name": "Canada",
        "code": "CA",
        "url": "https://iptvcat.com/canada__6",
    },
    "uk": {
        "name": "United Kingdom",
        "code": "GB",
        "url": "https://iptvcat.com/united_kingdom__11",
    },
}
DOWNLOAD_PATH = re.compile(r"^/my_list/s/[A-Za-z0-9_-]+\.m3u8?$", re.I)
HEADERS = {
    "User-Agent": "JGJG-TV-Radio-feed-refresh/1.0 (+https://github.com/bitsbb01/roku-tv-radio-feeds)",
    "Accept": "text/html,application/text,application/x-mpegURL,*/*",
}


@dataclass(frozen=True)
class PlaylistEntry:
    extinf: str
    url: str


def get_text(url: str, *, html: bool = False, allow_404: bool = False) -> str:
    headers = dict(HEADERS)
    if html:
        headers["Accept"] = "text/html,application/xhtml+xml"
    last_error = None
    for attempt in range(4):
        try:
            response = requests.get(url, headers=headers, timeout=(15, 45))
            if response.status_code == 404 and allow_404:
                return ""
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")


def channel_downloads(html: str, page_url: str) -> list[tuple[str, str]]:
    """Return (download URL, online status) for page entries."""
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        absolute = urljoin(page_url, link["href"])
        parsed = urlparse(absolute)
        if parsed.hostname not in {"list.iptvcat.com", "iptvcat.com"}:
            continue
        if not DOWNLOAD_PATH.match(parsed.path):
            continue

        status = ""
        row = link.find_parent("tr")
        previous = row.find_previous_sibling("tr") if row else None
        if previous:
            for cell in previous.find_all(["td", "th"], recursive=False):
                text = cell.get_text(" ", strip=True)
                if text in {"+", "-"}:
                    status = text
                    break
        found[absolute] = status
    return list(found.items())


def country_page_url(base: str, page: int) -> str:
    return base if page == 1 else f"{base.rstrip('/')}/{page}"


def collect_downloads(country: dict) -> tuple[list[str], int]:
    links: list[str] = []
    seen_page_fingerprints: set[tuple[str, ...]] = set()
    pages = 0
    for number in range(1, MAX_PAGES + 1):
        url = country_page_url(country["url"], number)
        html = get_text(url, html=True, allow_404=(number > 1))
        if not html:
            break
        page_links = channel_downloads(html, url)
        if not page_links:
            break

        fingerprint = tuple(link for link, _ in page_links)
        # Stop if an out-of-range page redirects to any earlier page.
        if fingerprint in seen_page_fingerprints:
            break
        seen_page_fingerprints.add(fingerprint)
        pages += 1
        # Omit rows IPTV Cat explicitly marks offline. Keep rows if the page
        # markup doesn't expose a status value so a layout change won't hide channels.
        links.extend(link for link, status in page_links if status != "-")
        logging.info("%s page %d: %d channel links", country["name"], number, len(page_links))
        time.sleep(0.6)
    else:
        raise RuntimeError(f"{country['name']} exceeded the {MAX_PAGES}-page safety limit")
    return list(dict.fromkeys(links)), pages


def parse_m3u(text: str) -> list[PlaylistEntry]:
    entries: list[PlaylistEntry] = []
    pending_extinf: str | None = None
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            pending_extinf = line
        elif line.startswith("#"):
            continue
        elif pending_extinf and line.lower().startswith(("http://", "https://", "rtmp://", "rtsp://")):
            entries.append(PlaylistEntry(pending_extinf, line))
            pending_extinf = None
    return entries


def fetch_entry(item: tuple[int, str]) -> tuple[str, list[PlaylistEntry]]:
    index, url = item
    time.sleep(0.25)
    try:
        entries = parse_m3u(get_text(url))
        return url, entries
    except Exception as exc:
        logging.warning("Skipping download %d: %s", index, exc)
        return url, []


def merge_entries(downloads: list[str]) -> list[PlaylistEntry]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        results = list(pool.map(fetch_entry, enumerate(downloads, start=1)))
    by_source = {url: entries for url, entries in results}

    # Retain the listing order for stable Roku browsing.
    output: list[PlaylistEntry] = []
    seen_urls: set[str] = set()
    for source_url in downloads:
        for entry in by_source.get(source_url, []):
            if entry.url in seen_urls:
                continue
            seen_urls.add(entry.url)
            output.append(entry)
    return output


def make_all_entry(entry: PlaylistEntry, country: dict) -> PlaylistEntry:
    line = entry.extinf
    for key, value in (("tvg-country", country["code"]), ("group-title", country["name"])):
        replacement = f'{key}="{value}"'
        pattern = re.compile(rf'(?<![\w-]){re.escape(key)}="[^"]*"')
        if pattern.search(line):
            line = pattern.sub(replacement, line, count=1)
        else:
            comma = line.find(",")
            if comma >= 0:
                line = line[:comma] + " " + replacement + line[comma:]
    return PlaylistEntry(line, entry.url)


def write_playlist(path: Path, entries: list[PlaylistEntry]) -> None:
    lines = ["#EXTM3U"]
    for entry in entries:
        lines.extend((entry.extinf, entry.url))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).replace('"', "'").strip()


def archive_item_entry(document: dict) -> PlaylistEntry | None:
    identifier = clean_text(document.get("identifier"))
    if not identifier:
        return None
    license_url = clean_text(document.get("licenseurl"))
    if "publicdomain" not in license_url.lower():
        return None

    time.sleep(0.2)
    response = requests.get(
        f"https://archive.org/metadata/{quote(identifier, safe='')}",
        headers=HEADERS,
        timeout=(15, 45),
    )
    response.raise_for_status()
    metadata_record = response.json()
    metadata = metadata_record.get("metadata") or {}
    item_license = clean_text(metadata.get("licenseurl") or license_url)
    if "publicdomain" not in item_license.lower():
        return None

    files = metadata_record.get("files") or []
    candidates = []
    for file_info in files:
        name = str(file_info.get("name") or "")
        if not name.lower().endswith(".mp4"):
            continue
        if str(file_info.get("private", "")).lower() in {"true", "1"}:
            continue
        try:
            size = int(file_info.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        lower_name = name.lower()
        score = 0
        if "512kb" in lower_name or "256kb" in lower_name:
            score += 30
        if "h264" in lower_name or "h.264" in lower_name:
            score += 20
        if size and size < 1_500_000_000:
            score += 10
        if size:
            score += max(0, 10 - int(size / 500_000_000))
        candidates.append((score, name))
    if not candidates:
        return None

    candidates.sort(reverse=True)
    filename = candidates[0][1]
    title = clean_text(document.get("title")) or identifier
    year = clean_text(document.get("year"))
    if year and year not in title:
        title = f"{title} ({year})"
    logo = f"https://archive.org/services/img/{quote(identifier, safe='')}"
    stream = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(filename, safe='/')}"
    extinf = (
        f'#EXTINF:-1 tvg-id="ia-{identifier}" tvg-logo="{logo}" '
        f'group-title="Internet Archive - Public Domain label",{title}'
    )
    return PlaylistEntry(extinf, stream)


def build_archive_feed() -> list[PlaylistEntry]:
    query = "mediatype:movies AND licenseurl:http*publicdomain*"
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
    payload = response.json()
    documents = (payload.get("response") or {}).get("docs") or []
    logging.info("Internet Archive search returned %d candidates", len(documents))

    results: list[PlaylistEntry] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(archive_item_entry, document) for document in documents]
        for future in concurrent.futures.as_completed(futures):
            try:
                entry = future.result()
                if entry is not None:
                    results.append(entry)
            except Exception as exc:
                logging.warning("Skipping Internet Archive item: %s", exc)

    # Keep API ranking order for a stable, familiar catalog.
    by_id = {}
    for entry in results:
        match = re.search(r'tvg-id="ia-([^"]+)"', entry.extinf)
        if match:
            by_id[match.group(1)] = entry
    ordered = []
    seen = set()
    for document in documents:
        identifier = clean_text(document.get("identifier"))
        if identifier in by_id and identifier not in seen:
            ordered.append(by_id[identifier])
            seen.add(identifier)
    return ordered


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    combined: list[PlaylistEntry] = []
    report = {
        "source": "IPTV Cat public country listings",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "countries": {},
    }

    try:
        for key, country in COUNTRIES.items():
            downloads, pages = collect_downloads(country)
            logging.info("%s: %d source M3Us across %d pages", country["name"], len(downloads), pages)
            entries = merge_entries(downloads)
            minimum = MIN_ENTRIES[key]
            if len(entries) < minimum:
                raise RuntimeError(
                    f"{country['name']} produced {len(entries)} valid entries; "
                    f"minimum safety threshold is {minimum}"
                )

            write_playlist(OUTPUT / f"{key}.m3u8", entries)
            combined.extend(make_all_entry(entry, country) for entry in entries)
            report["countries"][key] = {
                "name": country["name"],
                "pages": pages,
                "download_links": len(downloads),
                "channels": len(entries),
                "feed": f"playlists/{key}.m3u8",
            }
            logging.info("%s: wrote %d channels", country["name"], len(entries))

        try:
            archive_entries = build_archive_feed()
            if len(archive_entries) >= 20:
                write_playlist(OUTPUT / "archive_movies.m3u8", archive_entries)
                report["internet_archive"] = {
                    "channels": len(archive_entries),
                    "feed": "playlists/archive_movies.m3u8",
                    "filter": "Uploader-assigned public-domain license label",
                }
                logging.info("Wrote Internet Archive movie feed with %d items", len(archive_entries))
            else:
                logging.warning("Internet Archive returned only %d playable labeled items; preserving the prior feed", len(archive_entries))
        except Exception:
            logging.exception("Internet Archive refresh failed; preserving the last successful Archive feed")

        write_playlist(OUTPUT / "all.m3u8", combined)
        report["combined_channels"] = len(combined)
        (OUTPUT / "status.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        logging.info("Wrote combined feed with %d channels", len(combined))
        return 0
    except Exception:
        logging.exception("Refresh failed; feeds won't be committed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
