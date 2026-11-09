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
- Internet Archive cartoon preview playlist: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/archive_cartoons_review.m3u8
- Refresh status: https://raw.githubusercontent.com/bitsbb01/roku-tv-radio-feeds/main/playlists/status.json

The scraper walks IPTV Cat's public country pages, follows their per-channel M3U download links, skips rows IPTV Cat explicitly marks offline, and merges the remaining playlists. It also builds a separate Internet Archive movie feed by searching for items with an uploader-assigned public-domain license URL and selecting an MP4 file. That label is not an Archive guarantee of copyright status; the feed displays the label clearly, and individual items should be reviewed before wider distribution. Stream formats and availability can change.

The Internet Archive cartoon updater refreshes a JSON catalogue of search candidates and an M3U review-preview feed daily. The preview playlist includes only items whose uploader metadata reports a public-domain or Creative Commons license URL and whose item currently has a public MP4; every preview is labeled as unverified and is for checking the title/video on a private Roku only. These metadata labels are not approval: Internet Archive says it cannot guarantee uploader-provided rights information. After checking the actual item and confirming rights, add its identifier to `playlists/archive_cartoons_approved.txt`; the separate approved M3U is generated from that list.

## Refreshing

GitHub Actions refreshes the feeds daily and can also be started manually from the **Actions** tab using **Refresh IPTV Cat Feeds**. The workflow only commits generated files after all three country feeds pass minimum-size checks, so a blocked or incomplete scrape won't replace the last successful feeds.

The **Refresh Internet Archive Cartoons** workflow updates the candidate catalogue and review-preview playlist daily, then rebuilds the separate approved playlist when the approved identifier list changes.

The scraper uses a small number of concurrent requests and pauses between country pages and channel downloads. Please keep the scheduled refresh to once a day.

## Source

Channel names, logos, metadata, and stream URLs are collected from IPTV Cat's publicly accessible listings. IPTV Cat states that it re-shares links hosted elsewhere and does not host or stream the videos. This repository republishes those playlist entries for use by the JGJG Roku app.
