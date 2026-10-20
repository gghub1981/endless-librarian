# Endless Librarian

A small local web app for the **Polyend Endless** pedal on macOS. It shows every
plate (`.endl` effect) in your library with its picture and description, lets you
search and filter by category, and loads an effect onto the pedal with one click.

- Browse the free community plates from [polyend.com/plates](https://polyend.com/plates/), plus your own effects
- **Load Effect** copies the plate to the pedal's `ENDLESS` USB drive
- "In the pedal" strip shows which effect you loaded last
- Knob view: the pedal drawn with each plate's knob and footswitch functions, with draggable knobs
- Presets: save knob positions per plate as a note to yourself (the pedal can't report or set its knobs)
- Favorites, search, category chips, and Compare to view two plates side by side
- **Keep Alive** for Macs that unmount the pedal after a while

Runs entirely on your Mac at `http://127.0.0.1:8765`. It needs only the `python3`
that comes with macOS: no installs and no accounts.

> Unofficial project, not affiliated with Polyend. Plates and their pictures belong
> to their authors and are downloaded straight from polyend.com by the setup script;
> none of them are included in this repository.

## Setup

1. **Get the code.** On this page click **Code > Download ZIP**, then unzip it
   wherever you want to keep your library (for example in Documents). Or clone it:
   `git clone <this repo's URL>`.
2. **Install Python if asked.** The first time you run it, macOS may offer to install
   the Command Line Developer Tools, which include `python3`. Click **Install**.
3. **Download the plates.** Right-click **Setup.command** and choose **Open**, then
   click **Open** again in the warning. (macOS blocks double-clicking scripts
   downloaded from the internet the first time; after this you can double-click.)
   A Terminal window downloads every community plate into `Community/<category>/`
   and the pedal picture into `app/`. Run it again later to add newly published plates.
4. **Start the librarian.** Right-click **Start Librarian.command** > **Open** the same
   way. Your browser opens the app. Keep the Terminal window open while you use it;
   close it to stop the app.
5. **Connect the pedal** over USB. The header turns green when the `ENDLESS` drive
   is mounted. The first time you load an effect, macOS may ask whether Terminal can
   access a removable volume: click **Allow**.

After **Load Effect** the pedal reloads, and macOS may warn that the disk wasn't
ejected properly. That's expected.

If double-clicking a `.command` file says you don't have permission, open Terminal
in the folder and run `chmod +x *.command` once. You can also run everything by
hand: `python3 app/setup.py`, then `python3 app/server.py`.

## Your own effects

Put your own plates in the **My Effects** folder (setup creates it), each as up to
three files with the same name:

```
My Effects/
  Space Filter.endl      the effect
  Space Filter.jpg       optional picture (.jpg, .png, .webp or .gif)
  Space Filter.txt       optional info, format below
```

They show up under the **My Effects** chip and under their own categories. Any
other folder you add next to `Community` works too and gets its own 📁 chip.

### Info file format

```
Space Filter
Categories: Filter, Modulation
https://example.com/optional-link

A short description of the effect.

Knob controls:
- Cutoff – Filter frequency.
- Resonance – Peak at the cutoff.
- Drive – Input gain into the filter.

Footswitch controls:
- Short press – Envelope on/off.
- Long press – Freeze.
```

Line 1 is the title, then an optional `Categories:` line and an optional URL. The
three knob lines (in X, Y, A order) and the footswitch lines are drawn on the
pedal in the knob view; everything else is shown as the description.

## Settings

Set these as environment variables before starting `app/server.py` if the defaults
don't suit you:

| Variable | Default | What it does |
| --- | --- | --- |
| `ENDLESS_LIBRARY` | this folder | Where your plate folders are |
| `ENDLESS_DRIVE` | `/Volumes/ENDLESS` | Where the pedal mounts |
| `LIBRARIAN_PORT` | `8765` | Local web port |
| `LIBRARIAN_MY_FOLDER` | `My Effects` | Folder name for your own effects |

## Privacy

Everything stays on your Mac. Favorites, presets and the last loaded effect are
saved as small JSON files next to the app and your plates, and `.gitignore` keeps
them, the downloaded plates and your own effects out of git.

## License

MIT, see [LICENSE](LICENSE).
