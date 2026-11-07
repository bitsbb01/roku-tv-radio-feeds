# JGJG TV & Radio Feeds

Public, automatically refreshed M3U playlists for the Roku TV & Radio app.

## Feeds

- United States: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/usa.m3u8
- Canada: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/canada.m3u8
- United Kingdom: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/uk.m3u8
- Combined: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/all.m3u8
- Refresh status: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/status.json

The scraper walks IPTV Cat's public country pages, follows their per-channel M3U download links, skips rows IPTV Cat explicitly marks offline, and merges the remaining playlists. IPTV Cat's channel data and stream availability can change at any time; a listed stream may still fail at playback.

## Refreshing

GitHub Actions refreshes the feeds daily and can also be started manually from the **Actions** tab using **Refresh IPTV Cat Feeds**. The workflow only commits generated files after all three country feeds pass minimum-size checks, so a blocked or incomplete scrape won't replace the last successful feeds.

The scraper uses a small number of concurrent requests and pauses between country pages and channel downloads. Please keep the scheduled refresh to once a day.

## Source

Channel names, logos, metadata, and stream URLs are collected from IPTV Cat's publicly accessible listings. IPTV Cat states that it re-shares links hosted elsewhere and does not host or stream the videos. This repository republishes those playlist entries for use by the JGJG Roku app.
