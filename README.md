# Lyric IPA Finder

A vowel and diction tool for singers working on musical theatre and classical repertoire. Paste lyrics, click a word, get its IPA breakdown, vowel chart position, and articulation notes. Inline hints mark up the full lyrics so you can see diction issues across the whole phrase at once.

**This is a personal project built with LLM assistance. The singing tips are algorithmically generated and not verified. Cross-check anything important with your teacher!**

---

## Getting a release

Download the latest release from the GitHub releases page. The zip includes the script and an `Audio/` folder with vowel sound files. Extract and run.

If you want to run from source:

```
pip install PyQt5 svgwrite eng_to_ipa
```

Linux only: install `espeak-ng` for the Speak button.

```
sudo apt install espeak-ng
```

---

## Quick start

1. Pick or create a song slot from the dropdown at the top of the lyrics panel
2. Paste your lyrics
3. Click any word to open its analysis on the right
4. Coloured highlights will appear on words with diction notes; hover to read them

---

## Lyrics panel

**Clicking a word** opens its full analysis in the right panel.

**Right-clicking a word** gives you:

- *Set custom IPA* - override the dictionary. Use this for proper nouns, foreign words, and numbers the dictionary gets wrong. Enter without slashes, e.g. `valʒɑ̃` not `/valʒɑ̃/`
- *Toggle sustained note* - marks the word for long-note tips in the analysis panel (vibrato handling, vowel-specific warnings for high sustained pitches)
- *Dismiss hint* - hides the inline annotation for that word in this song permanently

**CLASSICAL / MT/CCM button** sets the style for the active song. This changes how aggressive some tips are: R toxicity is a hard warning in classical, a soft note in MT/CCM; vowel-to-vowel glide insertion is presented as standard practice in MT/CCM and as one option among two in classical.

**HINTS button** opens a menu:

- *Hints enabled* - master toggle
- *Enable all types / Disable all types* - bulk control
- Individual type checkboxes below

**Song menu** has:

- *Bulk Import IPAs* - paste a JSON object like `{"valjean": "valʒɑ̃", "cosette": "kɔzɛt"}` to set multiple overrides at once
- *Generate IPA Prompt to Clipboard* - builds a prompt for unrecognised words you can paste to an AI, then import the returned JSON via Bulk Import
- *Reset Dismissed Hints* - restores all dismissed annotations for the active song
- *Open Save Folder* - opens the folder where songs.json lives

**View menu** has font size and UI scale controls. Both persist across restarts.

---

## Inline hint types

Background tints on words in the lyrics editor. Hover to read the tip. Right-click to dismiss.

| Colour | Type | What it flags |
|---|---|---|
| Amber | Legato link | Word ends in a consonant, next word starts with a vowel. Carry the consonant across. |
| Green | Vowel glide | Word ends on a vowel, next starts on a vowel. Insert /j/ or /w/ to avoid a glottal stop. |
| Orange | Consonant crash | Adjacent stops or stop-into-nasal collision at a word boundary. |
| Red | R toxicity | Trailing /r/ or r-coloured vowel (/ɚ/, /ɝ/). De-rhotacize for classical/legit. |
| Steel blue | Dark L | Trailing /l/. Keep the tongue tip forward on the alveolar ridge. |
| Purple | Phrase-initial glottal | Phrase or line opens on a vowel. Use a balanced onset rather than a hard glottal strike (unless intentional). |
| Coral | Plosive exit | Trailing stop consonant. Snap off cleanly; no shadow vowel. |
| Teal | Nasal / voiced fricative exit | Consonant that carries pitch. Can be sustained for expressive weight. |
| Blue | Approximant exit | /l/, /w/, /j/, /r/ exit. Specific advice per consonant. |
| Lavender | Fricative exit | Voiced fricatives flagged as sustain resources; unvoiced flagged as air-dump risks. |

Punctuation (`,;:.!?`) suppresses legato tips at phrase boundaries. The word "the" automatically resolves to /ði/ before a vowel and /ðə/ before a consonant, in both the analysis panel and the phrase trajectory.

All types can be turned off individually from the HINTS menu.

---

## Phrase trajectory

A colour bar below the lyrics editor showing every vowel in the current line, warm for bright vowels and cool for dark ones. Gaps separate words. Click a syllable vowel button in the analysis panel to highlight its position in the bar.

Two automatic warnings appear below the bar:

- **Chiaroscuro** - fires when the line average brightness is very skewed in either direction, with a note on how to counter-balance
- **Breath support** - fires when more than 55% of the line's consonants are unvoiced, indicating phrases that drain air support quickly

Both thresholds are heuristic and somewhat arbitrary. Treat them as prompts to pay attention, not hard rules.

---

## Analysis panel

**Word label + Speak button** - Speak reads the word using the currently selected pronunciation. On Windows it uses SAPI SSML with IPA input, so custom pronunciations like `valʒɑ̃` are passed directly to the synthesiser. macOS uses `say` (no IPA support). Linux uses `espeak-ng`.

**PRONUNCIATIONS** - multiple pronunciations are shown with brightness tags. Click to select. Your choice is saved per song.

**SYLLABLE VOWELS** - one button per vowel in the selected pronunciation. Clicking highlights that vowel on the chart and in the trajectory bar.

**Vowel chart** - IPA trapezoid. Selected vowel shown as a filled circle. High-pitch modification targets shown with a dashed arrow. Diphthongs show the sustain-to-glide arc.

**Articulation card** - tongue position, lip shape, brightness bar, singing notes, and a stress warning when the selected vowel is on an unstressed syllable. If the word is marked as sustained (via right-click), a sustained-note section appears with vowel-specific tips and a vibrato note.

**Panel tips** - amber and blue-grey bars below the IPA label showing the same tip text as the hover tooltip for this word, so you can read it without hovering.

---

## What gets saved per song

Each song slot remembers:

- Lyrics
- Custom IPA overrides
- Preferred pronunciation choices
- Dismissed hints
- Sustained word marks
- Style setting (Classical / MT/CCM)

Song data is stored in a single `songs.json` file. Use **Song > Open Save Folder** to find it. The exact path depends on your OS and how you launch the app.

---

## Audio files

The `Audio/` folder should be in the same directory as the script (or the app bundle if running a release). Vowel sound files are named by IPA symbol, e.g. `e.mp3`, `aI.mp3`. R-coloured vowels /ɚ/ and /ɝ/ fall back to /ə/ and /ɜ/ automatically if their files are missing. The release zip includes this folder pre-populated.