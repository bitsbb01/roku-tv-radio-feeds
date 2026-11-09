# JGJG TV & Radio Feeds

Public, automatically refreshed M3U playlists for the Roku TV & Radio app.

## Feeds

- United States: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/usa.m3u8
- Canada: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/canada.m3u8
- United Kingdom: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/uk.m3u8
- Combined: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/all.m3u8
- Internet Archive films: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/archive_movies.m3u8
- Internet Archive cartoons: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/archive_cartoons.m3u8
- Internet Archive cartoon review candidates: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/archive_cartoons_review.json
- Refresh status: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/status.json

The scraper walks IPTV Cat's public country pages, follows their per-channel M3U download links, skips rows IPTV Cat explicitly marks offline, and merges the remaining playlists. It also builds a separate Internet Archive movie feed by searching for items with an uploader-assigned public-domain license URL and selecting an MP4 file. That label is not an Archive guarantee of copyright status; the feed displays the label clearly, and individual items should be reviewed before wider distribution. Stream formats and availability can change.

The Internet Archive cartoon updater refreshes a JSON catalogue of search candidates once a day. Candidates are metadata only and are not playable in the Roku app. To approve a cartoon, verify the rights and a Roku-compatible video file, then add its Internet Archive identifier to `playlists/archive_cartoons_approved.txt`, one identifier per line. The updater rebuilds the Roku M3U only from those approved identifiers and checks that each item still has a public-domain or Creative Commons rights URL and an MP4 file. Internet Archive states that uploader-provided rights information is not guaranteed, so the approval list must be reviewed before adding entries.

## Refreshing

GitHub Actions refreshes the feeds daily and can also be started manually from the **Actions** tab using **Refresh IPTV Cat Feeds**. The workflow only commits generated files after all three country feeds pass minimum-size checks, so a blocked or incomplete scrape won't replace the last successful feeds.

The **Refresh Internet Archive Cartoons** workflow updates the cartoon candidate catalogue and approved Roku playlist daily, or after the approved identifier list changes.

The scraper uses a small number of concurrent requests and pauses between country pages and channel downloads. Please keep the scheduled refresh to once a day.

## Source

Channel names, logos, metadata, and stream URLs are collected from IPTV Cat's publicly accessible listings. IPTV Cat states that it re-shares links hosted elsewhere and does not host or stream the videos. This repository republishes those playlist entries for use by the JGJG Roku app.
