#!/usr/bin/env python3
"""Endless Librarian setup: downloads the free community plates from
https://polyend.com/plates/ into Community/<first category>/ and the pedal
photo used by the knob view.

Run:  python3 app/setup.py            (or double-click "Setup.command")
      python3 app/setup.py --force    re-download files that already exist

Each plate becomes three files with the same name: Name.endl, Name.jpg (or .png)
and Name.txt (title, "Categories: ...", product URL, description and controls).
Files that are already there are skipped, so running it again only adds new plates.
Downloads go through curl, which every Mac has, with a browser User-Agent
(polyend.com refuses requests without one). Uses only the Python standard library.
"""
import html
import os
import re
import subprocess
import sys
import urllib.parse
from html.parser import HTMLParser

APP_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.abspath(os.path.expanduser(os.environ.get("ENDLESS_LIBRARY", os.path.dirname(APP_DIR))))
COMMUNITY = os.path.join(LIBRARY, "Community")
PLATES_URL = "https://polyend.com/plates/"
PEDAL_URL = "https://polyend.com/wp-content/themes/polyend/assets/images/endless__preview.png"
PEDAL_FILE = os.path.join(APP_DIR, "endless__preview.png")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.0 Safari/605.1.15")
FORCE = "--force" in sys.argv


def curl(url, dest=None):
    """Fetch a URL. Returns the text, or True/False when saving to dest."""
    cmd = ["curl", "-sSfL", "--retry", "3", "-A", UA, url]
    if dest:
        tmp = dest + ".part"
        ok = subprocess.run(cmd + ["-o", tmp]).returncode == 0
        if ok:
            os.replace(tmp, dest)
        elif os.path.exists(tmp):
            os.remove(tmp)
        return ok
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode:
        raise RuntimeError(out.stderr.decode(errors="replace").strip() or "download failed")
    return out.stdout.decode("utf-8", errors="replace")


def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s)).strip()


def list_plates(page):
    """Tiles on the plates page: product URL, image URL, title, categories."""
    plates = []
    for m in re.finditer(r'<a\s[^>]*class="plate-product-tiles__tile[ "][^>]*>(.*?)</a>', page, re.S):
        tile = m.group(0)
        href = re.search(r'href="([^"]+)"', tile)
        img = re.search(r'<img[^>]*\ssrc="([^"]+)"', tile)
        title = re.search(r'__tile__title">(.*?)</div>', tile, re.S)
        sub = re.search(r'__tile__subtitle">(.*?)</div>', tile, re.S)
        if href and title:
            plates.append({
                "url": href.group(1),
                "img": img.group(1) if img else None,
                "title": clean(title.group(1)),
                "categories": [c.strip() for c in clean(sub.group(1) if sub else "").split(",") if c.strip()],
            })
    return plates


class TextOf(HTMLParser):
    """HTML fragment -> plain text: paragraphs on their own lines, list items as '- '."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.out.append("\n- ")
        elif tag in ("p", "div", "ul", "ol", "h2", "h3", "h4"):
            self.out.append("\n\n")
        elif tag == "br":
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("p", "ul", "ol"):
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(re.sub(r"\s+", " ", data))

    def text(self):
        lines = [l.strip() for l in "".join(self.out).splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def to_text(fragment):
    p = TextOf()
    p.feed(fragment)
    return p.text()


def div_body(page, cls):
    m = re.search(r'<div class="%s">(.*?)</div>\s*(?=<div|</div)' % re.escape(cls), page, re.S)
    return m.group(1) if m else ""


def read_product(page):
    endl = re.search(r'href="([^"]+\.endl)"', page)
    author = clean(div_body(page, "single-plate__content__author"))
    desc = to_text(div_body(page, "single-plate__content__description"))
    details = to_text(div_body(page, "single-plate__content__details"))
    return endl.group(1) if endl else None, author, desc, details


def safe_name(s):
    return re.sub(r'[/:\\]', "_", s).strip() or "plate"


def main():
    os.makedirs(COMMUNITY, exist_ok=True)
    os.makedirs(os.path.join(LIBRARY, "My Effects"), exist_ok=True)
    print("Library: %s" % LIBRARY)

    if FORCE or not os.path.isfile(PEDAL_FILE):
        print("Pedal image ... ", end="", flush=True)
        print("ok" if curl(PEDAL_URL, PEDAL_FILE) else "not available, using the drawn pedal instead")

    print("Reading %s" % PLATES_URL)
    try:
        plates = list_plates(curl(PLATES_URL))
    except RuntimeError as e:
        sys.exit("Could not read the plates page: %s" % e)
    if not plates:
        sys.exit("No plates found on the page; the site layout may have changed.")
    print("%d plates listed\n" % len(plates))

    added = skipped = failed = 0
    for n, p in enumerate(plates, 1):
        label = "[%d/%d] %s" % (n, len(plates), p["title"])
        folder = os.path.join(COMMUNITY, safe_name(p["categories"][0] if p["categories"] else "Other"))
        try:
            endl_url, author, desc, details = read_product(curl(p["url"]))
        except RuntimeError as e:
            print("%s: page failed (%s)" % (label, e))
            failed += 1
            continue
        if not endl_url:
            print("%s: no download link, skipped" % label)
            failed += 1
            continue
        os.makedirs(folder, exist_ok=True)
        endl_name = safe_name(urllib.parse.unquote(os.path.basename(urllib.parse.urlparse(endl_url).path)))
        stem = os.path.splitext(endl_name)[0]
        endl_path = os.path.join(folder, endl_name)
        if os.path.isfile(endl_path) and not FORCE:
            skipped += 1
            continue
        if not curl(endl_url, endl_path):
            print("%s: .endl download failed" % label)
            failed += 1
            continue
        if p["img"]:
            ext = os.path.splitext(urllib.parse.urlparse(p["img"]).path)[1].lower() or ".jpg"
            curl(p["img"], os.path.join(folder, stem + ext))
        body = [p["title"], "Categories: " + ", ".join(p["categories"]), p["url"], ""]
        if author:
            body += [author, ""]
        body += [desc, "", details]
        with open(os.path.join(folder, stem + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(body).strip() + "\n")
        added += 1
        print("%s: added to %s" % (label, os.path.relpath(folder, LIBRARY)))

    print("\nDone. %d added, %d already there, %d failed." % (added, skipped, failed))


if __name__ == "__main__":
    main()
