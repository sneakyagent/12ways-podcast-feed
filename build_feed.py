#!/usr/bin/env python3
"""
Odysee -> Apple Podcasts feed rewriter for "12 Ways To Stop Aging".

Odysee's channel RSS is already a valid podcast feed, but it hardcodes
"<channel> on Odysee" as the title and serves WebP artwork that is under
Apple's 1400px floor. This rewrites just those parts and leaves the episode
list untouched, so new Odysee uploads still flow through automatically.
"""

import re
import sys
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime

CHANNEL = "@12WaysToStopAging"
CLAIM = "dc6c797a885e86e9087d8d9c51fa0def8147915c"
SOURCE = f"https://odysee.com/$/rss/{CHANNEL}:{CLAIM}"

SHOW_TITLE = "12 Ways To Stop Aging"
ODYSEE_TITLE = f"{SHOW_TITLE} on Odysee"

SEASON = 1

# Odysee emits no season/episode tags, so Apple files everything under
# "Unknown Season" and never shows episode numbers. This is a numbered
# 12-part series, so we stamp them ourselves: oldest pubDate is episode 1.
#
# That is correct as long as episodes go up in order. If one is ever
# published out of sequence, pin it here by its Odysee claim id instead
# and it will win over the chronological numbering.
EPISODE_OVERRIDES = {
    # "272ff29bf20bf7655fd82d38dd40558ea5a163d4": 1,
}

# Trailers must NOT take an episode number, or every real episode after them
# shifts by one. Anything whose claim id is listed here, or whose title reads
# like a trailer, is tagged itunes:episodeType=trailer and skipped when
# numbering. Pin by claim id when you can — the title check is a safety net.
TRAILER_CLAIMS = set()
TRAILER_WORDS = ("trailer", "intro to the series", "series intro")


def is_trailer(item, claim):
    if claim in TRAILER_CLAIMS:
        return True
    m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
    title = (m.group(1) if m else "").lower()
    return any(w in title for w in TRAILER_WORDS)

BASE = "https://sneakyagent.github.io/12ways-podcast-feed"
COVER_URL = f"{BASE}/cover-3000.jpg"
SELF_URL = f"{BASE}/feed.xml"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "12WaysFeedBuild/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def number_episodes(xml):
    """Add itunes:season/episode/episodeType to each item, oldest first."""
    items = re.findall(r"<item>.*?</item>", xml, flags=re.S)
    if not items:
        return xml

    def pub(it):
        m = re.search(r"<pubDate>(.*?)</pubDate>", it)
        return parsedate_to_datetime(m.group(1)) if m else datetime.min

    def claim(it):
        m = re.search(r"<guid[^>]*>[^<]*:([0-9a-f]{40})</guid>", it)
        return m.group(1) if m else None

    # Trailers are excluded from the sequence so they consume no number.
    episodes = [it for it in items if not is_trailer(it, claim(it))]
    order = {id(it): n for n, it in enumerate(sorted(episodes, key=pub), start=1)}

    for it in items:
        if "<itunes:episode>" in it or "<itunes:episodeType>" in it:
            continue
        if is_trailer(it, claim(it)):
            tags = "<itunes:episodeType>trailer</itunes:episodeType>"
        else:
            num = EPISODE_OVERRIDES.get(claim(it), order[id(it)])
            tags = (
                f"<itunes:season>{SEASON}</itunes:season>"
                f"<itunes:episode>{num}</itunes:episode>"
                f"<itunes:episodeType>full</itunes:episodeType>"
            )
        xml = xml.replace(it, it.replace("</item>", tags + "</item>"), 1)
    return xml


def build(xml):
    # Title, in both the CDATA and plain forms Odysee emits.
    xml = xml.replace(f"<![CDATA[{ODYSEE_TITLE}]]>", f"<![CDATA[{SHOW_TITLE}]]>")
    xml = xml.replace(f"<title>{ODYSEE_TITLE}</title>", f"<title>{SHOW_TITLE}</title>")

    # Artwork: every itunes:image -> compliant 3000px PNG.
    xml = re.sub(r'<itunes:image[^>]*?/>', f'<itunes:image href="{COVER_URL}"/>', xml)

    # Plain RSS <image><url> too, so directories agree.
    xml = re.sub(r'(<image>\s*<url>)[^<]*(</url>)', rf'\1{COVER_URL}\2', xml, flags=re.S)

    # rel=self should point at this feed, not the upstream one.
    xml = re.sub(r'<atom:link[^>]*rel="self"[^>]*/>',
                 f'<atom:link href="{SELF_URL}" rel="self" type="application/rss+xml"/>',
                 xml)

    # Season/episode numbering, which Odysee never provides.
    return number_episodes(xml)


if __name__ == "__main__":
    out = build(fetch(SOURCE))
    dest = sys.argv[1] if len(sys.argv) > 1 else "feed.xml"
    with open(dest, "w") as f:
        f.write(out)
    print(f"wrote {dest} ({len(out)} bytes)", file=sys.stderr)
