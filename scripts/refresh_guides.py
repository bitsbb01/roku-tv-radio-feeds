#!/usr/bin/env python3
"""Publish small, plain XMLTV guides for the Roku app.

The upstream sources publish several guides as standalone .xml.gz downloads.
Roku's XML parser cannot parse those compressed bytes, so this job streams each
feed, retains only channels present in the matching app playlist, and writes
plain XML suitable for the player.
"""
from __future__ import annotations

import gzip
import logging
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "guides"
HEADERS = {"User-Agent": "JGJG-TV-Radio-EPG/1.0"}
MAIN = "https://raw.githubusercontent.com/BuddyChewChew/buddylive-combined/refs/heads/main/combined_playlist.m3u"
BASE = "https://raw.githubusercontent.com/BuddyChewChew"
SOURCES = {
    "main": (MAIN, "https://epgshare01.online/epgshare01/epg_ripper_ALL_SOURCES1.xml.gz"),
    "pluto": (f"{BASE}/app-m3u-generator/main/playlists/plutotv_all.m3u", "https://github.com/matthuisman/i.mjh.nz/raw/master/PlutoTV/all.xml.gz"),
    "tubi": (f"{BASE}/app-m3u-generator/main/playlists/tubi_all.m3u", f"{BASE}/app-m3u-generator/main/playlists/tubi_epg.xml"),
    "localnow": ("https://www.apsattv.com/localnow.m3u", f"{BASE}/localnow-playlist-generator/main/epg.xml"),
    "xumo": (f"{BASE}/xumo-playlist-generator/main/playlists/xumo_playlist.m3u", f"{BASE}/xumo-playlist-generator/main/playlists/xumo_epg.xml.gz"),
    "airy": (f"{BASE}/airy-playlist-generator/main/airy_channels.m3u", f"{BASE}/airy-playlist-generator/main/airy_channels.xml"),
    "rakuten": (f"{BASE}/RakutenTV/main/playlist.m3u", f"{BASE}/RakutenTV/main/epg.xml"),
    "extra": (f"{BASE}/My-Streams/main/tv.m3u", "https://raw.githubusercontent.com/doms9/iptv/default/M3U8/TV.xml"),
    "plex_live": (f"{BASE}/app-m3u-generator/main/playlists/plex_all.m3u", "https://github.com/matthuisman/i.mjh.nz/raw/master/Plex/all.xml.gz"),
    "roku": (f"{BASE}/app-m3u-generator/main/playlists/roku_all.m3u", "https://github.com/matthuisman/i.mjh.nz/raw/master/Roku/all.xml.gz"),
    "tcl": (f"{BASE}/tcl-playlist-generator/main/tcl.m3u8", f"{BASE}/tcl-playlist-generator/main/tcl_epg.xml"),
    "country_us": ("https://iptv-org.github.io/iptv/countries/us.m3u", "https://epgshare01.online/epgshare01/epg_ripper_US1.xml.gz"),
    "country_ca": ("https://iptv-org.github.io/iptv/countries/ca.m3u", "https://epgshare01.online/epgshare01/epg_ripper_CA1.xml.gz"),
    "country_uk": ("https://iptv-org.github.io/iptv/countries/gb.m3u", "https://epgshare01.online/epgshare01/epg_ripper_UK1.xml.gz"),
}

def get_response(url: str) -> requests.Response:
    last = None
    for attempt in range(4):
        try:
            response = requests.get(url, headers=HEADERS, stream=True, timeout=(20, 180))
            response.raise_for_status()
            response.raw.decode_content = False
            return response
        except requests.RequestException as exc:
            last = exc
            if attempt < 3:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed to fetch {url}: {last}")

def playlist_ids(url: str) -> set[str]:
    response = get_response(url)
    try:
        text = response.content.decode("utf-8-sig", errors="replace")
    finally:
        response.close()
    ids = set()
    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            match = re.search(r'\btvg-id="([^"]+)"', line, re.I)
            if match and match.group(1).strip():
                ids.add(match.group(1).strip().casefold())
    return ids

def local_time(value: str) -> datetime | None:
    match = re.match(r"^(\d{14})", value or "")
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def write_filtered_guide(url: str, ids: set[str], destination: Path) -> tuple[int, int]:
    response = get_response(url)
    source = response.raw
    if urlparse(url).path.lower().endswith(".gz"):
        source = gzip.GzipFile(fileobj=response.raw)
    now = datetime.now(timezone.utc)
    earliest, latest = now - timedelta(hours=3), now + timedelta(days=2)
    channels = programmes = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("wb") as output:
            output.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="JGJG Roku Guide">\n')
            for _, element in ET.iterparse(source, events=("end",)):
                tag = element.tag.rsplit("}", 1)[-1].lower()
                if tag == "channel":
                    channel_id = (element.attrib.get("id") or "").casefold()
                    if channel_id in ids:
                        output.write(ET.tostring(element, encoding="utf-8"))
                        output.write(b"\n")
                        channels += 1
                    element.clear()
                elif tag == "programme":
                    channel_id = (element.attrib.get("channel") or "").casefold()
                    if channel_id in ids:
                        start = local_time(element.attrib.get("start", ""))
                        stop = local_time(element.attrib.get("stop", ""))
                        if start is None or stop is None or (stop >= earliest and start <= latest):
                            output.write(ET.tostring(element, encoding="utf-8"))
                            output.write(b"\n")
                            programmes += 1
                    element.clear()
                if output.tell() > 90_000_000:
                    raise RuntimeError(f"{destination.name} exceeded the 90 MB output safety limit")
            output.write(b"</tv>\n")
    finally:
        response.close()
    return channels, programmes

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    OUT.mkdir(parents=True, exist_ok=True)
    status = {"updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "feeds": {}}
    failed = []
    for name, (playlist_url, guide_url) in SOURCES.items():
        try:
            ids = playlist_ids(playlist_url)
            if not ids:
                raise RuntimeError("playlist contains no tvg-id values")
            channels, programmes = write_filtered_guide(guide_url, ids, OUT / f"{name}.xml")
            status["feeds"][name] = {"playlist_ids": len(ids), "guide_channels": channels, "programmes": programmes, "url": guide_url}
            logging.info("%s: %d channel IDs, %d guide channels, %d programmes", name, len(ids), channels, programmes)
            if programmes == 0:
                failed.append(name)
        except Exception as exc:
            logging.exception("%s guide refresh failed", name)
            status["feeds"][name] = {"error": str(exc), "url": guide_url}
            failed.append(name)
    (OUT / "status.json").write_text(__import__("json").dumps(status, indent=2) + "\n", encoding="utf-8")
    if failed:
        logging.error("Guide feeds with no programmes or errors: %s", ", ".join(failed))
    # Preserve the last valid guide for any individual source; failures are
    # recorded in status.json and do not prevent healthy sources refreshing.
    return 0

if __name__ == "__main__":
    sys.exit(main())
