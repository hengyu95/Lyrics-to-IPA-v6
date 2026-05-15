# Lyric IPA Finder

A singing-focused vowel and diction coach for musical theatre and classical singers. Paste lyrics, click any word, and get immediate IPA breakdowns, vowel chart positioning, and articulation advice.

---

## Requirements

```
PyQt5
PyQtMultimedia   # bundled with most PyQt5 installs
PyQtSvg          # for the vowel chart (falls back to an img tag if absent)
svgwrite
eng_to_ipa
```

Install:
```bash
pip install PyQt5 svgwrite eng_to_ipa
```

On Linux, install `espeak-ng` for the Speak button:
```bash
sudo apt install espeak-ng
```

---

## Features

### Lyrics Editor (left panel)

**Click any word** to open its full analysis in the right panel.

**Right-click any word** for two options:
- *Set custom IPA* — override the dictionary pronunciation. Essential for proper nouns (Valjean → `valʒɑ̃`), prisoner numbers (24601 → `twɛnti fɔr sɪks oʊ wʌn`), and any word the dictionary gets wrong.
- *Dismiss hint* — remove the inline annotation for that word permanently for this song.

**Inline hints** appear as background-tinted highlights on words with diction notes. Hover any highlighted word for the tip text. Eight categories, all individually toggleable:

| Colour | Hint type | What it flags |
|---|---|---|
| Amber | Legato link | Consonant-to-vowel boundary — carry the consonant across |
| Green | Vowel glide | Vowel-to-vowel boundary — insert /j/ or /w/ to avoid a glottal stop |
| Orange | Consonant crash | Adjacent stop/nasal collision — hold, elide, or merge |
| Red | R toxicity | Rhotacized vowel or trailing /r/ — de-rhotacize for tone |
| Steel blue | Dark L trap | Trailing /l/ — keep tongue tip forward, don't swallow |
| Purple | Phrase-initial glottal | Phrase opens on a vowel — use balanced onset, not a strike |
| Coral | Plosive exit | Snap off; no shadow vowel |
| Teal | Nasal exit | Carries pitch; sustain through it |
| Blue | Approximant exit | Gentle release |
| Lavender | Fricative exit | Control the airstream |

**HINTS button** (top-right of Lyrics panel): click to open a menu.
- *Hints enabled* — master on/off toggle
- *Enable all types / Disable all types* — bulk control
- Per-type checkboxes below for surgical control

**Song → Reset Dismissed Hints** restores all dismissed words for the active song.

---

### Phrase Trajectory (below the editor)

A horizontal color bar showing every vowel in the clicked word's line, colored by acoustic brightness (warm = bright/forward, cool = dark/back). Gaps separate words.

**Click a syllable vowel button** in the right panel to spotlight its position in the phrase trajectory — useful for planning the tone-color arc of a line.

Three automatic warnings appear below the bar when triggered:
- **Chiaroscuro imbalance** — the line average is too bright (shrillness risk) or too dark (muffled risk), with specific counter-balance advice
- **Breath leak warning** — high unvoiced consonant density (>55%) drains air support quickly; engage intercostals actively
- **Sibilance warning** — three or more sibilants flagged with separate advice for mic and hall contexts

---

### Analysis Panel (right panel)

**Word label + ▶ Speak** — the Speak button reads the word aloud using the *currently selected pronunciation*, not the default dictionary form. On Windows this uses SAPI SSML with IPA phoneme input, so custom pronunciations like Valjean's are rendered accurately. On macOS it uses `say`, on Linux `espeak-ng`.

**PRONUNCIATIONS** — when a word has multiple valid pronunciations, each is shown with a brightness tag (brighter/darker) and a coloured left border. Click to select. Your preferred pronunciation is remembered per song and persists to the save file.

**SYLLABLE VOWELS** — round buttons for each vowel in the selected pronunciation. Click to highlight that vowel on the chart and in the trajectory bar.

**Vowel chart** — the IPA trapezoid. The selected vowel is highlighted with a filled circle. If the vowel has a high-pitch modification target, a dashed arrow points to it. Diphthongs show a curved arc from primary to glide vowel.

**Articulation card** — below the chart:
- Full name, tongue height and advancement, lip shape
- Brightness bar (dark ←→ bright)
- Singing notes
- Stress warning (⚠) when the selected vowel is on an unstressed syllable
- Modification ladder for high pitch (e.g. /i/ → /ɪ/ → nothing)

**Panel tips** (amber and blue-gray bars under the IPA label) — same text as the inline annotation hover tooltip for the selected word. Legato/glide/crash tips appear in amber; consonant release/R toxicity tips in blue-gray.

---

### Consonant intelligence

The app understands diction rules at word boundaries, not just within words:

| Situation | Detection | Advice |
|---|---|---|
| Consonant → next-word vowel | Legato link | Carry the consonant; don't lift |
| Vowel → next-word vowel | Glide insertion | /j/ after front vowels, /w/ after back/round |
| Stop → same stop | Geminate | Hold; release once |
| Stop → nasal | Elision | Drop the plosive completely |
| Stop → different stop | Hold-through | Release only on second plosive |
| Line/phrase opens on vowel | Glottal onset | Balanced onset (appoggio), not strike |
| Trailing /r/ or rhotic vowel | R toxicity | De-rhotacize |
| Trailing /l/ | Dark L | Tongue tip forward |

Punctuation (`,;:.!?`) suppresses legato tips at phrase boundaries.

The smart *the* rule: "the" resolves to /ðə/ before a consonant and /ði/ before a vowel, automatically, both in the panel and the trajectory bar.

---

## Songs and saving

Songs are stored as named save slots in a local JSON file. Each song remembers:
- Lyrics
- Custom IPA overrides (per word)
- Preferred pronunciation choices (per word)
- Dismissed inline hints (per word)

**Song → Bulk Import IPAs…** — paste a JSON object to import many overrides at once:
```json
{"valjean": "valʒɑ̃", "cosette": "kɔzɛt"s}
```

**Song → Generate IPA Prompt to Clipboard** — scans the lyrics for unrecognized words and builds a prompt ready to paste to an AI, which returns JSON you can bulk-import.

**Song → Open Save Folder** — opens the data directory in Explorer/Finder/Files.

---

## View settings

- **Adjust Lyrics Font Size…** — changes only the editor font; panel UI is unaffected
- **Adjust UI Scale…** — scales all label, button, and panel text from 75% to 200% in 25% steps

Both settings apply immediately and persist for the session. On 4K displays the app auto-scales all pixel values to the screen's device pixel ratio.

---

## Audio

Place `.mp3` files named by IPA symbol in an `Audio/` folder next to the script (e.g. `Audio/ɛ.mp3`, `Audio/eɪ.mp3`). The **▶ Play vowel sound** button plays the selected vowel. R-colored vowels /ɚ/ and /ɝ/ fall back to /ə/ and /ɜ/ if their own files are absent.

---

## Keyboard shortcut ideas (not yet implemented)

- Next word in line → `Tab`
- Previous word → `Shift+Tab`
- Cycle pronunciation → `Alt+↑/↓`
- Speak word → `Alt+S`

---

## Data location

| Platform | Path |
|---|---|
| Windows | `%LOCALAPPDATA%\Heng\LyricIPAFinder\songs.json` |
| macOS | `~/Library/Application Support/Heng/LyricIPAFinder/songs.json` |
| Linux | `~/.local/share/Heng/LyricIPAFinder/songs.json` |
