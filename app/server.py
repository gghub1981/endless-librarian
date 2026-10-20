#!/usr/bin/env python3
"""Endless Librarian: a small local server for browsing plates and loading
them onto the Polyend Endless (mounted as the ENDLESS drive).

Run:  python3 app/server.py   (or double-click "Start Librarian.command")
Then open http://127.0.0.1:8765
Uses only the Python standard library.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("LIBRARIAN_PORT", "8765"))
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# The library folder holding Community/, My Effects/ and any other plate folders: the repo root by default.
ENDLESS_DIR = os.path.abspath(os.path.expanduser(os.environ.get("ENDLESS_LIBRARY", os.path.dirname(APP_DIR))))
DRIVE = os.environ.get("ENDLESS_DRIVE", "/Volumes/ENDLESS")
PEDAL_IMAGE = "endless__preview.png"  # top view of the pedal (downloaded by setup.py), used under the controls
PEDAL_FALLBACK = "pedal.svg"  # plain drawing used when the photo isn't there
OURS = os.environ.get("LIBRARIAN_MY_FOLDER", "My Effects")  # folder name (anywhere in the library) for your own effects
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif")
MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
    ".json": "application/json", ".txt": "text/plain; charset=utf-8",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml", ".endl": "application/octet-stream",
}

try:
    with open(os.path.join(APP_DIR, "plate-images.json")) as f:
        IMAGE_MAP = json.load(f)  # endl path -> image path, for names that don't match
except (OSError, ValueError):
    IMAGE_MAP = {}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def find_image(rel_endl, folder_files):
    mapped = IMAGE_MAP.get(rel_endl)
    if mapped and os.path.exists(os.path.join(ENDLESS_DIR, mapped)):
        return mapped
    stem = norm(os.path.splitext(os.path.basename(rel_endl))[0])
    folder = os.path.dirname(rel_endl)
    for f in folder_files:
        if f.lower().endswith(IMAGE_EXTS) and norm(os.path.splitext(f)[0]) == stem:
            return folder + "/" + f
    return None


def read_info(path):
    """Info .txt: line 1 title, 'Categories: a, b', a URL, then the description."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except OSError:
        return {}
    info = {"title": lines[0].strip() if lines else ""}
    body_start = 1
    for i, line in enumerate(lines[1:4], start=1):
        if line.lower().startswith("categories:"):
            info["categories"] = [c.strip() for c in line.split(":", 1)[1].split(",") if c.strip()]
            body_start = i + 1
        elif line.startswith("http"):
            info["url"] = line.strip()
            body_start = i + 1
    info["text"], knobs, info["switch"] = split_controls("\n".join(lines[body_start:]))
    # Always 3 knobs; fall back to the pedal's own labels when the text doesn't name them.
    info["knobs"] = knobs + [{"name": n, "desc": ""} for n in ["X", "Y", "A"][len(knobs):]]
    return info


HEADER = re.compile(r"(?i)^(knobs?|knob controls|controls|foot-?switch(es)?|foot-?switch controls|expression( pedal)?)\b")
SPLIT = re.compile(r"\s+[–—-]\s+|\s*:\s+")


def split_controls(text):
    """Pull the knob / footswitch / expression sections out of an info text.
    Returns (remaining text, knobs [{name, desc}], switch [{name, desc}])."""
    knobs, switch, keep, knob_lines = [], [], [], []
    section, items, dash = None, None, False
    for line in text.splitlines():
        s = line.strip()
        if dash and s:
            s, line, dash = "- " + s, "- " + s, False
        if section and s == "-":
            dash = True
            continue
        h = HEADER.match(s)
        if h and (s.endswith(":") or len(s) < 30 or s.lower().startswith("expression")):
            word = h.group(1).lower()
            section = "exp" if word.startswith("exp") else "switch" if "switch" in word else "knobs"
            items = {"knobs": knobs, "switch": switch}.get(section)
            if section == "knobs":
                knob_lines.append(line)
            continue
        if section is None:
            keep.append(line)
            continue
        if not s:
            continue
        if section == "knobs" and (s[:1] in "-•*" or line[:1].isspace()):
            knob_lines.append(line)
        if s[:1] in "-•*":
            body = s[1:].strip()
            letter = re.match(r"^([XYA]):", body) if section == "knobs" else None
            body = re.sub(r"^[XYA]:\s*", "", body) if section == "knobs" else body
            parts = SPLIT.split(body, maxsplit=1)
            if len(parts) == 2 and len(parts[0]) <= 30:
                name, desc = parts
            elif len(body) > 30:
                name, _, desc = body.partition(" ")
            else:
                name, desc = body, ""
            if items is not None:
                item = {"name": name.strip().rstrip("."), "desc": desc.strip()}
                role = re.search(r"\s*\((primary|secondary)\)\s*$", item["name"], re.I)
                if role and section == "knobs":
                    item["name"] = item["name"][:role.start()]
                    item["role"] = role.group(1).lower()
                    item["letter"] = letter.group(1) if letter else ""
                items.append(item)
        elif items and (line[:1].isspace() or section == "exp"):
            items[-1]["desc"] = (items[-1]["desc"] + " " + s).strip()
        elif section == "exp":
            continue
        else:
            # A plain paragraph after the controls lists: back to normal text.
            section, items = None, None
            keep.append(line)
    if any(k.get("role") == "secondary" for k in knobs):
        knobs = merge_knob_layers(knobs)
        # Two functions per knob don't fit under the knobs, so the full list stays in the text too.
        keep += [""] + knob_lines
    rest = re.sub(r"\n{3,}", "\n\n", "\n".join(keep)).strip()
    return rest, knobs[:3], switch


def merge_knob_layers(knobs):
    """Knobs listed as 'X: Time (primary)' and 'X: Feedback (secondary)' become one knob
    'Time / Feedback' whose note is the first phrase of each description."""
    merged = []
    for letter in "XYA":
        layer = [k for k in knobs if k.get("letter") == letter]
        layer.sort(key=lambda k: k.get("role") != "primary")
        if not layer:
            continue
        short = [re.split(r"[,;.]", k["desc"], maxsplit=1)[0].strip() for k in layer]
        merged.append({"name": " / ".join(k["name"] for k in layer),
                       "desc": " / ".join(t for t in short if t)})
    return merged


def presets_path(endl_path):
    return os.path.splitext(endl_path)[0] + ".presets.json"


def load_presets(endl_path):
    try:
        with open(presets_path(endl_path)) as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


FAVORITES_FILE = os.path.join(APP_DIR, "favorites.json")


def load_favorites():
    try:
        with open(FAVORITES_FILE) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def save_favorites(favs):
    tmp = FAVORITES_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(favs), f, indent=1)
    os.replace(tmp, FAVORITES_FILE)


def scan_plates():
    favs = load_favorites()
    plates = []
    for root, dirs, files in os.walk(ENDLESS_DIR):
        dirs[:] = sorted(d for d in dirs if d != os.path.basename(APP_DIR) and not d.startswith("."))
        for f in sorted(files):
            if not f.lower().endswith(".endl"):
                continue
            rel = os.path.relpath(os.path.join(root, f), ENDLESS_DIR).replace(os.sep, "/")
            parts = rel.split("/")
            stem = os.path.splitext(f)[0]
            info = read_info(os.path.join(root, stem + ".txt"))
            folder_cat = parts[-2] if len(parts) >= 3 else ""
            categories = info.get("categories") or ([folder_cat] if folder_cat and folder_cat != OURS else [])
            # Your own effects live in a "My Effects" folder; they always get that category too.
            mine = OURS.lower() in (p.lower() for p in parts[:-1])
            types = [c for c in categories if c != OURS]
            if mine:
                categories = [OURS] + types
            plates.append({
                "id": rel,
                "file": f,
                "source": parts[0] if len(parts) > 1 else "",
                "title": info.get("title") or stem,
                "categories": categories,
                "mine": mine,
                "types": types,
                "favorite": rel in favs,
                "knobs": info.get("knobs") or [{"name": n, "desc": ""} for n in "XYA"],
                "switch": info.get("switch", []),
                "presets": load_presets(os.path.join(root, f)),
                "url": info.get("url"),
                "text": info.get("text", ""),
                "image": find_image(rel, files),
                "size": os.path.getsize(os.path.join(root, f)),
            })
    return plates


# The pedal installs a copied .endl and then clears it from its drive, so the drive alone
# can't tell what's loaded. Remember the last effect we saw or sent, across app restarts.
ACTIVE_FILE = os.path.join(APP_DIR, "active.json")


def load_active():
    try:
        with open(ACTIVE_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_active(file, plate_id=None):
    data = {"file": file, "id": plate_id, "t": time.time()}
    try:
        tmp = ACTIVE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, ACTIVE_FILE)
    except OSError:
        pass
    last_loaded.update(data)


last_loaded = load_active()


def drive_status():
    """The active effect: the newest .endl still on the drive, else the last one remembered."""
    mounted = os.path.isdir(DRIVE)
    files = []
    if mounted:
        try:
            files = [f for f in os.listdir(DRIVE) if f.lower().endswith(".endl") and not f.startswith(".")]
            files.sort(key=lambda f: os.path.getmtime(os.path.join(DRIVE, f)))
        except OSError:
            files = []
    if files and last_loaded.get("file") not in files:
        save_active(files[-1])  # copied some other way, e.g. dragged in Finder
    return {"mounted": mounted, "path": DRIVE, "files": sorted(files),
            "active": last_loaded.get("file"), "active_id": last_loaded.get("id")}


KEEPALIVE_EVERY = 10  # seconds
keepalive = {"on": False, "last_ok": None, "events": [], "caffeinate": None}


def touch_drive():
    """Read a few bytes from a file on the pedal, bypassing the Mac's cache, so
    the drive sees real USB traffic. Never writes: writes make the pedal reload."""
    files = [f for f in os.listdir(DRIVE) if not f.startswith(".")]
    files = [f for f in files if os.path.isfile(os.path.join(DRIVE, f))]
    if not files:
        os.statvfs(DRIVE)
        return
    fd = os.open(os.path.join(DRIVE, files[0]), os.O_RDONLY)
    try:
        if sys.platform == "darwin":
            import fcntl
            fcntl.fcntl(fd, 48, 1)  # F_NOCACHE
        os.read(fd, 512)
    finally:
        os.close(fd)


def set_caffeinate(on):
    """caffeinate -m stops macOS from idling the disk while Keep Alive is on."""
    proc = keepalive["caffeinate"]
    if on and proc is None and shutil.which("caffeinate"):
        keepalive["caffeinate"] = subprocess.Popen(["caffeinate", "-m", "-w", str(os.getpid())])
    elif not on and proc is not None:
        proc.terminate()
        keepalive["caffeinate"] = None


def log_event(text):
    keepalive["events"] = (keepalive["events"] + [{"t": time.time(), "text": text}])[-20:]


def keepalive_loop():
    was_mounted = os.path.isdir(DRIVE)
    while True:
        mounted = os.path.isdir(DRIVE)
        if mounted != was_mounted:
            log_event("ENDLESS connected" if mounted else "ENDLESS disconnected")
            was_mounted = mounted
        if keepalive["on"] and mounted:
            try:
                touch_drive()
                keepalive["last_ok"] = time.time()
            except OSError:
                pass
        time.sleep(KEEPALIVE_EVERY)


def keepalive_status():
    return {"on": keepalive["on"], "last_ok": keepalive["last_ok"], "events": keepalive["events"],
            "every": KEEPALIVE_EVERY}


def safe_path(rel):
    full = os.path.realpath(os.path.join(ENDLESS_DIR, rel))
    if not full.startswith(os.path.realpath(ENDLESS_DIR) + os.sep):
        return None
    return full


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/pedal.png":
            photo = os.path.join(APP_DIR, PEDAL_IMAGE)
            return self.send_file(photo if os.path.isfile(photo) else os.path.join(APP_DIR, PEDAL_FALLBACK))
        if path in ("/", "/index.html"):
            return self.send_file(os.path.join(APP_DIR, "index.html"))
        if path == "/api/plates":
            return self.send_json({"plates": scan_plates(), "drive": drive_status(), "mine_label": OURS})
        if path == "/api/drive":
            return self.send_json(dict(drive_status(), keepalive=keepalive_status()))
        if path.startswith("/files/"):
            full = safe_path(urllib.parse.unquote(path[len("/files/"):]))
            if full and os.path.isfile(full):
                return self.send_file(full)
        self.send_error(404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path not in ("/api/load", "/api/keepalive", "/api/favorite", "/api/presets"):
            return self.send_error(404)
        # Only accept requests from this page, not from other websites.
        origin = self.headers.get("Origin", "")
        if origin and not re.match(r"^http://(127\.0\.0\.1|localhost):%d$" % PORT, origin):
            return self.send_json({"ok": False, "error": "Forbidden origin"}, 403)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except ValueError:
            return self.send_json({"ok": False, "error": "Bad request"}, 400)
        if path == "/api/presets":
            src = safe_path(str(req.get("id", "")))
            presets = req.get("presets")
            if not src or not src.lower().endswith(".endl") or not os.path.isfile(src) or not isinstance(presets, list):
                return self.send_json({"ok": False, "error": "Bad request"}, 400)
            dest = presets_path(src)
            tmp = dest + ".tmp"
            with open(tmp, "w") as f:
                json.dump(presets, f, indent=1)
            os.replace(tmp, dest)
            return self.send_json({"ok": True})
        if path == "/api/favorite":
            favs = load_favorites()
            pid = str(req.get("id", ""))
            if req.get("on"):
                favs.add(pid)
            else:
                favs.discard(pid)
            save_favorites(favs)
            return self.send_json({"ok": True, "favorite": pid in favs})
        if path == "/api/keepalive":
            keepalive["on"] = bool(req.get("on"))
            set_caffeinate(keepalive["on"])
            log_event("Keep Alive on" if keepalive["on"] else "Keep Alive off")
            return self.send_json(dict(keepalive_status(), ok=True))
        src = safe_path(req.get("id", ""))
        if not src or not src.lower().endswith(".endl") or not os.path.isfile(src):
            return self.send_json({"ok": False, "error": "Plate file not found"}, 404)
        if not os.path.isdir(DRIVE):
            return self.send_json({"ok": False, "error": "ENDLESS drive is not connected. Plug in the pedal over USB and try again."}, 409)
        dest = os.path.join(DRIVE, os.path.basename(src))
        try:
            shutil.copyfile(src, dest)
            with open(dest, "rb+") as f:
                os.fsync(f.fileno())
            if hasattr(os, "sync"):
                os.sync()
        except OSError as e:
            return self.send_json({"ok": False, "error": "Copy failed: %s" % e}, 500)
        save_active(os.path.basename(src), os.path.relpath(src, ENDLESS_DIR).replace(os.sep, "/"))
        return self.send_json({"ok": True, "dest": dest})


def main():
    try:
        server = HTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("Port %d is busy; the librarian is probably already running." % PORT)
        print("Open http://127.0.0.1:%d in your browser." % PORT)
        sys.exit(1)
    print("Endless Librarian running at http://127.0.0.1:%d" % PORT)
    print("Plates folder: %s" % ENDLESS_DIR)
    print("Pedal drive:   %s" % DRIVE)
    threading.Thread(target=keepalive_loop, daemon=True).start()
    print("Close this window (or press Ctrl+C) to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        set_caffeinate(False)


if __name__ == "__main__":
    main()
