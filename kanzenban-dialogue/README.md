# Kanzenban dialogue (experimental)

**Experimental.** This add-on has had only limited emulator testing. It has not
been played through, and it has not been tried on a real console. Keep your
unpatched image.

It ports dialogue that differs in the Saturn release (*Linda³ Kanzenban*) into
the v0.95.9 English PlayStation image, and adds the Saturn version of the
playing-doctor conversation in the Joint Playroom (Scenario A).

It does not use the Atlas build in this repository. It works on an image that
already has the v0.95.9 patch applied.

## Contents

| File | Purpose |
| --- | --- |
| `english-dialogue-draft.md` | The dialogue text, paired with its PlayStation counterparts. Edit this to revise wording. |
| `dialogue.py` | Applies the draft to every matching program bank and rebuilds `LINDA.MIC`. |
| `doctor_event.py` | The playing-doctor event for MIC slot 71, plus shared CD-sector helpers. |
| `verify.py` | Structural checks run during the build. |
| `build.py` | Runs everything and writes the image. |

## Building

You need Python 3.11 or later and the v0.95.9 English image as a single-track
raw BIN (MODE2/2352). If you have a CHD, extract it first:

```
chdman extractcd -i "Linda Again.chd" -o original.cue -ob original.bin
```

The BIN must have this SHA-256:

```
e65fd247ede8cc7d22cc032e2875e6ef82e78a08cc8f69c56e7dac3cc7902cf3
```

Then run, from this folder:

```
python -X utf8 build.py original.bin output
```

This writes `Kanzenban dialogue.bin`, a matching CUE and `build-report.json`
into `output`. It needs about 1.7 GB of memory and 810 MB of disk space. With
the draft as committed, the output SHA-256 is:

```
c265e8ec04cfb727a6d87b2ae2ce26c2e2d41f78453b34101334fca0fda35d9f
```

## What changes

- 55 draft entries are applied across 222 program banks. Most of that count is
  one repeated objective line.
- The surname Aumann becomes Koman.
- MIC slot 71 gains the garment question, Ken's reply and the Saturn comeback
  menu.
- MIC slot 600 (Kokubu graffiti) gains a small code hook that sets the age
  shown in the text.
- A complete rebuilt `LINDA.MIC` is appended to the end of the disc. Sectors 16
  and 23 are updated to point to it. Nothing else on the disc moves.

## Known limits

- The age shown in the Kokubu graffiti has not been checked in game.
- The doctor event was tested by warping into the room with the story
  conditions bypassed in emulator memory. Reaching it in normal play is
  untested.
- Most changed lines have not been viewed in game. New text is wrapped at 34
  characters and three rows per page, which is an estimate and not a
  measurement of the font.
- Replaced records may lose voice or timing commands that the original record
  carried.
- Two Saturn-only passages are not ported: the singing narration
  (`184@0x67CE`) and the Kokubu challenge introduction (`695@0x81FC`).
