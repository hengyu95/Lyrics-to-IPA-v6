# Lyric IPA Finder

A vowel and diction tool for singers working on musical theatre and classical repertoire. Paste lyrics, click a word, get its IPA breakdown, vowel chart position, and articulation notes. Inline hints mark up the full lyrics so you can see diction issues across the whole phrase at once.

**Personal project built with LLM assistance. The singing tips are algorithmically generated and not verified. Cross-check anything important with your teacher.**

---

## Installation

Download the latest `.exe` from the [releases page](../../releases). No installation needed, just run it.

---

## Quick start

1. Pick or create a song slot from the dropdown at the top of the lyrics panel
2. Paste your lyrics
3. Click any word to open its analysis on the right
4. Coloured highlights appear on words with diction notes; hover to read them

---

## Lyrics panel

**Click a word** to open its full analysis in the right panel.

**Right-click a word** for:

- *Set custom IPA* - override the dictionary pronunciation. Useful for proper nouns, foreign words, and numbers. Enter without slashes, e.g. `valʒɑ̃` not `/valʒɑ̃/`
- *Toggle sustained note* - marks a word for long-note tips in the analysis panel (vibrato handling, vowel-specific warnings)
- *Dismiss hint* - hides the inline annotation for that word permanently for this song

**CLASSICAL / MT/CCM button** sets the singing style for the active song. Affects how aggressive certain tips are: R toxicity is a hard warning in classical mode, a soft note in MT/CCM; vowel-to-vowel glide insertion is presented as standard practice in MT/CCM and as one option among two in classical.

**HINTS button** opens a menu with a master on/off toggle, bulk enable/disable, and per-type checkboxes for the ten annotation categories.

**Song menu:**

- *Bulk Import IPAs* - paste a JSON object like `{"valjean": "valʒɑ̃", "cosette": "kɔzɛt"}` to set multiple custom pronunciations at once
- *Generate IPA Prompt to Clipboard* - scans the lyrics for unrecognised words and builds a prompt you can paste into an AI; import the returned JSON via Bulk Import
- *Reset Dismissed Hints* - restores all dismissed annotations for the active song
- *Open Save Folder* - opens the folder containing `songs.json`

**View menu** has font size and UI scale controls. Both persist across restarts.

---

## Inline hint types

Background tints on words in the lyrics. Hover to read the tip. Right-click to dismiss.

| Colour | Type | What it flags |
|---|---|---|
| Amber | Legato link | Consonant-final word before a vowel-initial word. Carry the consonant across. |
| Green | Vowel glide | Vowel-final word before a vowel-initial word. Insert /j/ or /w/ to avoid a glottal stop. |
| Orange | Consonant crash | Stop-into-stop or stop-into-nasal at a word boundary. |
| Red | R toxicity | Trailing /r/ or r-coloured vowel (/ɚ/, /ɝ/). De-rhotacize for classical/legit. |
| Steel blue | Dark L | Trailing /l/. Keep the tongue tip forward; don't pull the root back. |
| Purple | Phrase-initial glottal | Phrase or line opens on a vowel. Use a balanced onset unless a glottal attack is intentional. |
| Coral | Plosive exit | Trailing stop. Snap off cleanly; no shadow vowel. |
| Teal | Nasal / voiced fricative exit | Pitch-carrying consonant. Can be sustained for expressive weight. |
| Blue | Approximant exit | /l/, /w/, /j/, /r/ exit. Advice differs per consonant. |
| Lavender | Fricative exit | Voiced fricatives flagged as sustain resources; unvoiced as air-dump risks. |

Punctuation (`,;:.!?`) suppresses legato tips at phrase boundaries. "the" automatically resolves to /ði/ before a vowel and /ðə/ before a consonant.

---

## Phrase trajectory

A colour bar below the lyrics showing every vowel in the current line, warm for bright vowels and cool for dark ones. Gaps separate words. Click a syllable vowel button in the analysis panel to highlight its position in the bar.

Two warnings appear below when triggered:

- **Chiaroscuro** - line average brightness is very skewed; suggests how to counter-balance
- **Breath support** - more than 55% of the line's consonants are unvoiced, which drains air support quickly

Both thresholds are rough heuristics. Treat them as prompts, not rules.

---

## Analysis panel

**Speak button** - reads the word using the currently selected pronunciation. Uses SAPI SSML with IPA input on Windows, so custom pronunciations like `valʒɑ̃` are passed directly to the synthesiser rather than guessed from spelling.

**PRONUNCIATIONS** - multiple pronunciations shown with brightness tags. Click to select. Preference is saved per song.

**SYLLABLE VOWELS** - one button per vowel in the selected pronunciation. Clicking highlights that vowel on the chart and in the trajectory bar.

**Vowel chart** - IPA trapezoid with the selected vowel highlighted. High-pitch modification targets shown with a dashed arrow. Diphthongs show the sustain-to-glide arc.

**Articulation card** - tongue position, lip shape, brightness bar, singing notes. Shows a stress warning when the selected vowel is on an unstressed syllable. If the word is marked as sustained (right-click in the lyrics), a sustained-note section appears with vowel-specific tips and vibrato notes.

**Panel tips** - same text as the hover tooltip for the current word, so you can read it without going back to the lyrics.

---

## Save data

Each song slot remembers lyrics, custom IPA overrides, preferred pronunciations, dismissed hints, sustained word marks, and the style setting. Everything is stored in a single `songs.json` file. Use **Song > Open Save Folder** to locate it.