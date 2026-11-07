# JGJG TV & Radio Feeds

Public, automatically refreshed M3U playlists for the Roku TV & Radio app.

## Feeds

- United States: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/usa.m3u8
- Canada: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/canada.m3u8
- United Kingdom: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/uk.m3u8
- Combined: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/all.m3u8
- Internet Archive films: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/archive_movies.m3u8
- Refresh status: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/status.json

The scraper walks IPTV Cat's public country pages, follows their per-channel M3U download links, skips rows IPTV Cat explicitly marks offline, and merges the remaining playlists. It also builds a separate Internet Archive movie feed by searching for items with an uploader-assigned public-domain license URL and selecting an MP4 file. That label is not an Archive guarantee of copyright status; the feed displays the label clearly, and individual items should be reviewed before wider distribution. Stream formats and availability can change.

## Refreshing

GitHub Actions refreshes the feeds daily and can also be started manually from the **Actions** tab using **Refresh IPTV Cat Feeds**. The workflow only commits generated files after all three country feeds pass minimum-size checks, so a blocked or incomplete scrape won't replace the last successful feeds.

The scraper uses a small number of concurrent requests and pauses between country pages and channel downloads. Please keep the scheduled refresh to once a day.

## Source

Channel names, logos, metadata, and stream URLs are collected from IPTV Cat's publicly accessible listings. IPTV Cat states that it re-shares links hosted elsewhere and does not host or stream the videos. This repository republishes those playlist entries for use by the JGJG Roku app.
