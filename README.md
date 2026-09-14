# 12 Ways To Stop Aging — podcast feed

Apple Podcasts pulls this feed. It is a thin rewrite of the channel's Odysee RSS.

**Feed URL:** https://sneakyagent.github.io/12ways-podcast-feed/feed.xml

## Why this exists

Odysee publishes a valid podcast feed at

```
https://odysee.com/$/rss/@12WaysToStopAging:dc6c797a885e86e9087d8d9c51fa0def8147915c
```

(note: the *full* 40-character claim id — the short one in the channel URL returns
"invalid"). Apple accepts it, but two things come through wrong:

- the title is hardcoded as "12 Ways To Stop Aging **on Odysee**"
- the artwork is a 1238x1238 WebP, under Apple's JPEG/PNG 1400-3000 requirement

`build_feed.py` rewrites exactly those two things and passes everything else
through untouched, so new Odysee uploads still appear automatically.

## How it stays current

`.github/workflows/refresh-feed.yml` rebuilds the feed hourly and commits it when
it changes. Apple then crawls this URL on its own schedule. To push an episode out
faster, run the workflow by hand from the Actions tab.

## Changing the artwork

Replace `cover-3000.jpg` (square, 1400-3000px, PNG or JPEG) and push.
