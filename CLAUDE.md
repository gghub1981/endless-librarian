# Endless Librarian: notes for coding agents

Local macOS web app for browsing Polyend Endless plates (`.endl`) and copying them to
the pedal. Python standard library only, one HTML file, no build step, no dependencies.

## Layout

```
Setup.command            runs app/setup.py (download community plates + pedal photo)
Start Librarian.command  stops any running copy on :8765, opens the browser, runs app/server.py
app/server.py            HTTP server on 127.0.0.1:8765: scans the library, serves files, JSON API
app/index.html           the whole UI (vanilla JS + CSS, Albert Sans from Google Fonts)
app/setup.py             scrapes polyend.com/plates via curl with a browser User-Agent
app/pedal.svg            drawn pedal, used when app/endless__preview.png is missing
Community/<Category>/    downloaded plates (gitignored)
My Effects/              the user's own plates (gitignored)
```

The library root is the repo root (parent of `app/`), or `ENDLESS_LIBRARY`. Every
subfolder except `app/` and hidden folders is scanned recursively for `.endl` files.

## A plate

`Name.endl` plus optional same-stem `Name.txt` and `Name.jpg|png|webp|gif`. Images
whose names differ can be mapped in an optional `app/plate-images.json`
(`{"Community/Delay/X.endl": "Community/Delay/x_pic.jpg"}`); setup.py names images to
match, so it normally isn't needed.

`.txt` format (parsed by `read_info` and `split_controls` in server.py):

- Line 1: title. Within the next 3 lines: `Categories: A, B` and/or a line starting with `http`.
- The rest is the description. Sections headed `Knob controls:` / `Knobs:`,
  `Footswitch controls:` and `Expression pedal` are pulled out: knob bullets
  (`- Name – desc`, also `- X: Name – desc`) become the 3 knob labels on the pedal
  image (X, Y, A in order), footswitch bullets become the switch notes, and the
  expression section is dropped.
- Two-layer knobs: `- X: Time (primary) – ...` and `- X: Feedback (secondary) – ...`
  merge into one label `Time / Feedback` (secondary in blue); the note is the first
  phrase of each desc, and the full knob list also stays in the description.

Categories come from the `.txt`, else from the parent folder name. Plates anywhere
under a folder named `My Effects` (`LIBRARIAN_MY_FOLDER`) also get that category
and `mine: true`.

## API (server.py)

- `GET /api/plates` → `{plates: [...], drive: {...}, mine_label}`; each plate has
  id (path relative to the library), title, categories, types, knobs, switch,
  presets, url, text, image, favorite, size.
- `GET /api/drive` → drive status + keep-alive status (polled by the UI).
- `GET /files/<rel path>` → any file inside the library (path-checked by `safe_path`).
- `GET /pedal.png` → `app/endless__preview.png` (940×1340) or `app/pedal.svg`.
- `POST /api/load {id}` → copies the `.endl` to the drive root, fsyncs, records it as active.
- `POST /api/favorite {id, on}`, `POST /api/presets {id, presets}`, `POST /api/keepalive {on}`.
  POSTs from other origins are rejected.

## Pedal behaviour worth knowing

- The pedal mounts as `/Volumes/ENDLESS` and runs the most recently copied `.endl`;
  it then deletes the file from its drive. So the last loaded effect is remembered in
  `app/active.json`, and a `.endl` seen on the drive overrides it.
- Never write to the drive except in Load: any write makes the pedal reload.
  Keep Alive only reads 512 bytes every 10 s with `F_NOCACHE` and runs `caffeinate -m`.
- The pedal can't report knob positions (no MIDI or file API), so presets are notes:
  `<plate>.presets.json` next to the `.endl`, `[{name, values: [x%, y%, a%]}]`.
- Favorites: `app/favorites.json`, a list of plate ids.

## UI notes (index.html)

- Knob centres on the pedal image: `KNOB_POS` (% of the 940×1340 image); the `*`
  switch ring is `.pedal .sw-mark`. Keep `pedal.svg` in sync if these move.
- Two side panes: `#panel` (main) and `#pin` (Compare), each with its own state in
  `state.panes.main` / `state.panes.pin`.
- Colours and type follow polyend.com/plates.

## Conventions

- Standard library only; keep it runnable with macOS's `/usr/bin/python3`.
- Don't commit plates, images, favorites, presets or `active.json` (see `.gitignore`).
- Test the parser by pointing `ENDLESS_LIBRARY` at a scratch folder and running
  `LIBRARIAN_PORT=8799 python3 app/server.py`, then `curl localhost:8799/api/plates`.
