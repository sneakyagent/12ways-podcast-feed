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

CHANNEL = "@12WaysToStopAging"
CLAIM = "dc6c797a885e86e9087d8d9c51fa0def8147915c"
SOURCE = f"https://odysee.com/$/rss/{CHANNEL}:{CLAIM}"

SHOW_TITLE = "12 Ways To Stop Aging"
ODYSEE_TITLE = f"{SHOW_TITLE} on Odysee"

BASE = "https://sneakyagent.github.io/12ways-podcast-feed"
COVER_URL = f"{BASE}/cover-3000.png"
SELF_URL = f"{BASE}/feed.xml"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "12WaysFeedBuild/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


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
    return xml


if __name__ == "__main__":
    out = build(fetch(SOURCE))
    dest = sys.argv[1] if len(sys.argv) > 1 else "feed.xml"
    with open(dest, "w") as f:
        f.write(out)
    print(f"wrote {dest} ({len(out)} bytes)", file=sys.stderr)
