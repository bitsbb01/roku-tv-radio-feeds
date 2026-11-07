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
from urllib.parse import urljoin, urlparse

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
