#!/usr/bin/env python3
"""
Odysee -> Apple Podcasts feed rewriter for "12 Ways To Stop Aging".

Odysee's channel RSS is already a valid podcast feed, but it hardcodes
"<channel> on Odysee" as the title and serves WebP artwork that is under
Apple's 1400px floor. This rewrites just those parts and leaves the episode
list untouched, so new Odysee uploads still flow through automatically.
"""

import os
import random
import re
import sys
import time
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
TRAILER_CLAIMS = {
    "e1cb37c111d9f83ebf892b2d0ec205d6447f20e7",  # 12 Ways To Stop Aging - Series Trailer
}
TRAILER_WORDS = ("trailer", "intro to the series", "series intro")

# Odysee serves the raw video at ~0.5 MB/s, so a 27-minute 1.17GB episode
# takes ~35 minutes to download and cannot stream in real time. Spotify also
# refuses any feed containing video ("We're unable to accept podcasts with
# videos"). So each item's enclosure is swapped for an MP3 served from this
# repo. The video stays on Odysee and is linked from the show notes.
#
# Key = Odysee claim id, value = path to the audio in this repo.
AUDIO_OVERRIDES = {
    "272ff29bf20bf7655fd82d38dd40558ea5a163d4": "media/ep01.mp3",
    "e1cb37c111d9f83ebf892b2d0ec205d6447f20e7": "media/trailer.mp3",
    "8ee204b2dc7a0b4771f33056b2448af47af913b8": "media/ep02.mp3",
}


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
    # Odysee's RSS sits behind a Cloudflare cache with a 1 hour TTL, so the
    # plain URL can serve a copy that predates a just-published episode --
    # observed serving 2 items while the origin had 3. A unique query string
    # makes it a cache MISS so we always build from what Odysee actually has.
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}cb={int(time.time())}-{random.randint(1000, 9999)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "12WaysFeedBuild/1.0", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def drop_unmapped_items(xml):
    """Remove items we have no audio for.

    A new Odysee upload appears in the feed with a video enclosure. Spotify
    rejects any feed containing video, and Apple cannot stream 1GB+ off
    Odysee, so letting one through would break both. Until its MP3 is added
    to AUDIO_OVERRIDES an item is simply held back.
    """
    def keep(m):
        item = m.group(0)
        if any(c in item for c in AUDIO_OVERRIDES):
            return item
        t = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.S)
        print(f"HOLDING BACK (no audio yet): {(t.group(1) if t else '?')[:60]}",
              file=sys.stderr)
        return ""

    return re.sub(r"<item>.*?</item>", keep, xml, flags=re.S)


def swap_enclosures(xml):
    """Replace each item's Odysee video enclosure with our hosted MP3."""
    for claim, path in AUDIO_OVERRIDES.items():
        if not os.path.exists(path):
            print(f"WARNING: {path} missing, leaving {claim} on video", file=sys.stderr)
            continue
        size = os.path.getsize(path)
        url = f"{BASE}/{path}"
        new = f'<enclosure url="{url}" length="{size}" type="audio/mpeg"/>'

        def repl(m, claim=claim, new=new):
            item = m.group(0)
            if claim not in item:
                return item
            return re.sub(r"<enclosure[^>]*/>", new, item)

        xml = re.sub(r"<item>.*?</item>", repl, xml, flags=re.S)
    return xml


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


def strip_html_breaks(xml):
    """Turn Odysee's literal <br /> tags into real line breaks.

    Odysee writes HTML into the description. Apple parses it, but Spotify
    renders it verbatim -- readers saw "...than they are?<br>How some 80
    year old..." in the show preview. Convert the breaks to newlines and
    drop the inline thumbnail <img>, which has no place in show notes.
    """
    def fix(m):
        body = m.group(1)
        body = re.sub(r"<img[^>]*/?>", "", body)
        body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
        body = re.sub(r"</?p[^>]*>", "\n", body, flags=re.I)
        body = re.sub(r"\n{3,}", "\n\n", body)
        return f"<description><![CDATA[{body.strip()}]]></description>"

    return re.sub(r"<description><!\[CDATA\[(.*?)\]\]></description>",
                  fix, xml, flags=re.S)


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

    # Odysee writes HTML into descriptions; Spotify renders it literally.
    xml = strip_html_breaks(xml)

    # Hold back anything we have no audio for, then swap the rest.
    xml = drop_unmapped_items(xml)
    xml = swap_enclosures(xml)

    # Season/episode numbering, which Odysee never provides.
    return number_episodes(xml)


def count_items(xml):
    return len(re.findall(r"<item>", xml))


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "feed.xml"
    out = build(fetch(SOURCE))
    fresh = count_items(out)

    # Odysee's RSS generator is eventually consistent: a freshly published
    # claim can appear in the feed, then drop out again for a while (observed
    # with the series trailer, and confirmed against origin with the CDN cache
    # bypassed). Rebuilding from one of those thin responses would delete
    # episodes from the feed Apple reads, and podcast apps handle episodes
    # vanishing badly. So never let a rebuild shrink the feed: if we got
    # fewer items than we are already serving, keep what we have and let
    # the next run try again.
    try:
        with open(dest) as f:
            current = f.read()
    except FileNotFoundError:
        current = ""

    # Only trust the existing feed if it is actually a feed. A file left
    # half-merged by git counts both sides' items, which made the guard
    # below "protect" a broken feed with conflict markers in it and refuse
    # every clean rebuild.
    if "<<<<<<<" in current or ">>>>>>>" in current or "<rss" not in current:
        if current:
            print("existing feed is corrupt; replacing it", file=sys.stderr)
        current = ""

    if current:
        have = count_items(current)
        if fresh < have:
            print(
                f"REFUSING to shrink feed: upstream returned {fresh} item(s), "
                f"currently serving {have}. Keeping existing feed.",
                file=sys.stderr,
            )
            sys.exit(0)

    with open(dest, "w") as f:
        f.write(out)
    print(f"wrote {dest} ({len(out)} bytes, {fresh} items)", file=sys.stderr)
