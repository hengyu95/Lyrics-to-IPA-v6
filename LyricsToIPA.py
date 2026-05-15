"""Lyric IPA Finder — singing-aware vowel coach.

Click any word in the lyrics to see its IPA breakdown, the position of each
vowel on the chart, articulation tips, and modification advice for higher
pitches. Diphthongs are surfaced as units with sustain/glide pedagogy.
When a word has multiple valid pronunciations, they're tagged
'brighter'/'darker' so you can make a conscious stylistic choice.

Right-click any word to set a custom IPA — useful for proper nouns like
"Valjean" and prisoner numbers like "24601" that aren't in the dictionary.
Songs are stored as named save slots; each remembers its lyrics and its
custom-IPA overrides.
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from io import StringIO
from os import path
from typing import Optional

# ── HiDPI must be set before QApplication is created ──────────────────────────
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')

from PyQt5.QtCore import (Qt, QUrl, QSettings, QStandardPaths, QTimer,
                          pyqtSignal)
from PyQt5.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPalette,
                         QTextCharFormat, QTextCursor)
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtWidgets import (QAction, QApplication, QComboBox, QDialog,
                             QDialogButtonBox, QFrame, QHBoxLayout,
                             QInputDialog, QLabel, QLineEdit, QMainWindow,
                             QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                             QScrollArea, QSizePolicy, QSplitter, QTextEdit,
                             QToolButton, QToolTip, QVBoxLayout, QWidget)
import svgwrite
import eng_to_ipa as ipa

try:
    from PyQt5.QtSvg import QSvgWidget
    HAS_QTSVG = True
except ImportError:
    HAS_QTSVG = False


# =============================================================================
# HiDPI scaling helpers  — call after QApplication exists
# =============================================================================

def _dpr() -> float:
    """Device pixel ratio of the primary screen (1.0 on normal displays,
    2.0 on Retina/4K with 200% scaling, etc.)."""
    screens = QApplication.screens()
    if screens:
        return screens[0].devicePixelRatio()
    return 1.0


def _scale(value: float) -> int:
    """Scale a logical pixel value by the device pixel ratio, rounded."""
    return max(1, round(value * _dpr()))


def _scalef(value: float) -> float:
    """Floating-point scale (for font sizes in pt, which Qt already handles,
    but useful when we need fractional precision)."""
    return value * _dpr()


# =============================================================================
# Vowel database
# =============================================================================

@dataclass(frozen=True)
class Vowel:
    symbol: str
    x: int            # 0 (front) to 250 (back) on the trapezoid
    y: int            # 0 (close/high) to 300 (open/low)
    rounded: bool
    name: str
    tongue_height: str
    tongue_advance: str
    lips: str
    singing_note: str
    mod_high: Optional[str]   # single-step modification target at high pitch


_V = [
    Vowel('i', 0,   0,   False, 'close front unrounded',
          'high', 'front', 'spread, neutral',
          "Bright and forward. Don't over-spread the lips on high notes — "
          "that thins the tone.",
          'ɪ'),
    Vowel('y', 0,   0,   True,  'close front rounded',
          'high', 'front', 'rounded',
          'Bright tongue, rounded lips. French "tu", German "über".',
          'ʏ'),
    Vowel('ɪ', 50,  50,  False, 'near-close near-front unrounded',
          'near-high', 'near-front', 'neutral',
          "A common modification target for /i/ — slightly relaxed and rounder.",
          None),
    Vowel('ʏ', 50,  50,  True,  'near-close near-front rounded',
          'near-high', 'near-front', 'slightly rounded',
          'Modification target for /y/.',
          None),
    Vowel('e', 17,  100, False, 'close-mid front unrounded',
          'mid-high', 'front', 'neutral to spread',
          "In legit/classical, often relaxes toward /ɛ/ as pitch rises. Rare "
          "alone in English — usually part of the diphthong /eɪ/.",
          'ɛ'),
    Vowel('ø', 17,  100, True,  'close-mid front rounded',
          'mid-high', 'front', 'rounded',
          'French "deux", German "schön".',
          'œ'),
    Vowel('ɛ', 34,  200, False, 'open-mid front unrounded',
          'mid-low', 'front', 'neutral',
          "A comfortable open-front vowel — usually doesn't need modification "
          "unless very high, in which case it can open further toward /a/.",
          None),
    Vowel('œ', 34,  200, True,  'open-mid front rounded',
          'mid-low', 'front', 'rounded',
          'French "neuf".',
          None),
    Vowel('æ', 43,  250, False, 'near-open front unrounded',
          'low', 'front', 'spread',
          "Bright but tense. Belt-friendly; classical singers modify toward "
          "/ɛ/ to avoid the pinched quality at high pitch.",
          'ɛ'),
    Vowel('a', 50,  300, False, 'open front unrounded',
          'low', 'front', 'neutral',
          "Open and bright. Release the jaw — don't lateral-spread.",
          None),
    Vowel('ɶ', 50,  300, True,  'open front rounded',
          'low', 'front', 'rounded',
          'Rare. Some Scandinavian languages.',
          None),
    Vowel('ɨ', 125, 0,   False, 'close central unrounded',
          'high', 'central', 'neutral',
          'Shadowy, neutral high vowel. Russian "ы".',
          'ə'),
    Vowel('ʉ', 125, 0,   True,  'close central rounded',
          'high', 'central', 'rounded',
          'Swedish "du"; many Australian English /u/ variants.',
          'ʊ'),
    Vowel('ɘ', 137, 100, False, 'close-mid central unrounded',
          'mid-high', 'central', 'neutral',
          "Near-schwa. Pass through it; don't color it.",
          'ə'),
    Vowel('ɵ', 137, 100, True,  'close-mid central rounded',
          'mid-high', 'central', 'slightly rounded',
          'Lightly rounded schwa region.',
          'ə'),
    Vowel('ə', 139, 150, False, 'mid central (schwa)',
          'mid', 'central', 'neutral',
          "The most neutral vowel — tongue and lips at rest. Many singers "
          "over-weight schwa; resist it. On stressed syllables a schwa usually "
          "wants to be /ʌ/ instead.",
          None),
    Vowel('ɜ', 141, 200, False, 'open-mid central unrounded',
          'mid-low', 'central', 'neutral',
          'British "bird". The base vowel underlying the American r-colored /ɝ/. '
          'For classical/legit singing, de-rhotacize American /ɝ/ toward this.',
          None),
    Vowel('ɝ', 141, 200, False, 'open-mid central unrounded (r-colored)',
          'mid-low', 'central', 'neutral with retroflex/bunched r',
          'American English stressed r-vowel: "bird", "word", "her" (when stressed). '
          'R-coloring is a tongue posture layered on top of /ɜ/ — the tongue tip '
          'curls back or the tongue body bunches. For classical and legit musical '
          'theatre singing, release the r-color and sustain on /ɜ/ instead. '
          'Plotted at the same position as /ɜ/ since the base articulation is identical.',
          'ɜ'),
    Vowel('ɚ', 139, 150, False, 'mid central (r-colored schwa)',
          'mid', 'central', 'neutral with retroflex/bunched r',
          'American English unstressed r-vowel: "butter", "your", "over". '
          'The rhotacized counterpart of schwa /ə/ — same neutral tongue position '
          'but with added r-coloring. For sustained singing, release the r and '
          'settle into plain /ə/. Plotted at the schwa position on the trapezoid.',
          'ə'),
    Vowel('ɞ', 141, 200, True,  'open-mid central rounded',
          'mid-low', 'central', 'rounded',
          'Rare.',
          None),
    Vowel('ɐ', 143, 250, False, 'near-open central unrounded',
          'low', 'central', 'neutral',
          'Central and open — a comfortable resonance space for high notes.',
          None),
    Vowel('ɯ', 250, 0,   False, 'close back unrounded',
          'high', 'back', 'neutral',
          'Back tongue without lip rounding — dark without warmth.',
          'ɤ'),
    Vowel('u', 250, 0,   True,  'close back rounded',
          'high', 'back', 'rounded',
          'The darkest common vowel. On high notes, open lips slightly '
          'toward /ʊ/ — pursing locks the resonance.',
          'ʊ'),
    Vowel('ʊ', 210, 50,  True,  'near-close near-back rounded',
          'near-high', 'near-back', 'rounded',
          'A relaxed back vowel. Modification target for /u/ at high pitches.',
          'o'),
    Vowel('ɤ', 250, 100, False, 'close-mid back unrounded',
          'mid-high', 'back', 'neutral',
          'Mandarin "ㄜ"; back, mid-high, unrounded.',
          'ʌ'),
    Vowel('o', 250, 100, True,  'close-mid back rounded',
          'mid-high', 'back', 'rounded',
          'Round and dark. Sustain by keeping internal space — never by pursing.',
          None),
    Vowel('ʌ', 250, 200, False, 'open-mid back unrounded',
          'mid-low', 'back', 'neutral',
          'American "cup". Often migrates toward /ɔ/ at high pitch.',
          'ɔ'),
    Vowel('ɔ', 250, 200, True,  'open-mid back rounded',
          'mid-low', 'back', 'rounded',
          "British \"thought\". Rich and round — chiaroscuro's dark pole.",
          None),
    Vowel('ɑ', 250, 300, False, 'open back unrounded',
          'low', 'back', 'neutral',
          'American "father". Open, dark, comfortable on high notes.',
          None),
    Vowel('ɒ', 250, 300, True,  'open back rounded',
          'low', 'back', 'rounded',
          'British "lot". Slight rounding adds warmth without darkening fully.',
          None),
]
VOWELS = {v.symbol: v for v in _V}


# Familiar word examples for each vowel
VOWEL_EXAMPLES = {
    'i':  'beet',     'ɪ':  'bit',
    'y':  'tu (Fr.)', 'ʏ':  'Glück (Ger.)',
    'e':  'café',     'ø':  'deux (Fr.)',
    'ɛ':  'bed',      'œ':  'neuf (Fr.)',
    'æ':  'cat',      'a':  'spa',
    'ɶ':  '(rare)',
    'ɨ':  '(Russian)', 'ʉ':  '(Swedish)',
    'ɘ':  '(near schwa)', 'ɵ': '(rounded schwa)',
    'ə':  'sofa',
    'ɜ':  'her (Br.)', 'ɝ': 'bird (Am.)', 'ɚ': 'butter (Am.)', 'ɞ': '(rare)',
    'ɐ':  'butter',
    'ɯ':  '(Mandarin)',
    'u':  'boot',     'ʊ':  'book',
    'ɤ':  '(Mandarin)',
    'o':  'no (Sp.)',
    'ʌ':  'cup',      'ɔ':  'thought',
    'ɑ':  'father',   'ɒ':  'lot (Br.)',
}


# =============================================================================
# Diphthong database
# =============================================================================

@dataclass(frozen=True)
class Diphthong:
    symbol: str       # 'eɪ', 'aɪ', etc.
    name: str
    example: str
    primary: str      # sustained vowel
    glide: str        # vanishing vowel
    singing_note: str
    mod_primary: Optional[str]


_DI = [
    Diphthong('eɪ', 'long-A diphthong', 'say, plain, day, way', 'e', 'ɪ',
              "Sustain on /e/ for nearly the whole duration. Glide to /ɪ/ only "
              "at the very last moment, like a vanishing tail. Rushing to the "
              "/ɪ/ is the most common amateur mistake on this vowel.",
              'ɛ'),
    Diphthong('aɪ', 'long-I diphthong', 'sky, mine, time, my', 'a', 'ɪ',
              'Sustain on /a/ (an open, bright vowel). Late vanish to /ɪ/. '
              'At very high pitch, the /a/ may open further toward /ɑ/.',
              'ɑ'),
    Diphthong('aʊ', 'OW diphthong', 'how, now, mouth, out', 'a', 'ʊ',
              'Sustain on /a/. Late vanish to /ʊ/. Keep the lips open through '
              'the sustain — they only round at the very end.',
              'ɑ'),
    Diphthong('oʊ', 'long-O diphthong', 'no, go, slow, hold', 'o', 'ʊ',
              'Sustain on /o/. The /ʊ/ tail is barely there — many classical '
              'singers omit it entirely and sustain pure /o/.',
              'ɔ'),
    Diphthong('ɔɪ', 'OI diphthong', 'boy, joy, voice', 'ɔ', 'ɪ',
              'Sustain on /ɔ/ (round and dark). Late vanish to /ɪ/. The shift '
              'between rounded and spread is dramatic — control the lip motion.',
              'o'),
    Diphthong('ɪə', 'EAR diphthong', 'here, near, dear (Br.)', 'ɪ', 'ə',
              'Brief /ɪ/ relaxing into schwa. Mostly British/RP transcription.',
              None),
    Diphthong('eə', 'AIR diphthong', 'there, hair, care (Br.)', 'e', 'ə',
              'Open /e/ relaxing into schwa. Mostly British/RP.', None),
    Diphthong('ʊə', 'POOR diphthong', 'tour, poor (Br.)', 'ʊ', 'ə',
              '/ʊ/ relaxing into schwa. Mostly British/RP.', None),
]
DIPHTHONGS = {d.symbol: d for d in _DI}


def get_phone(symbol: str):
    return DIPHTHONGS.get(symbol) or VOWELS.get(symbol)


# =============================================================================
# Common function words — sung weak forms
# =============================================================================

FUNCTION_WORDS = {
    'the':    ['ðə', 'ði'],
    'a':      ['ə', 'eɪ'],
    'an':     ['ən', 'æn'],
    'of':     ['əv', 'ʌv'],
    'to':     ['tə', 'tu'],
    'for':    ['fɚ', 'fɔɹ'],
    'and':    ['ən', 'ænd'],
    'but':    ['bət', 'bʌt'],
    'or':     ['ɚ', 'ɔɹ'],
    'as':     ['əz', 'æz'],
    'in':     ['ɪn'],
    'on':     ['ɑn'],
    'at':     ['ət', 'æt'],
    'is':     ['ɪz'],
    'was':    ['wəz', 'wʌz'],
    'are':    ['ɚ', 'ɑɹ'],
    'were':   ['wɚ'],
    'my':     ['maɪ'],
    'your':   ['jɚ', 'jɔɹ'],
    'his':    ['hɪz'],
    'her':    ['hɚ'],
    'our':    ['aʊɚ', 'ɑɹ'],
    'their':  ['ðɛɚ', 'ðɛɹ'],
    'them':   ['ðəm'],
    'us':     ['əs'],
    'him':    ['hɪm'],
    'will':   ['wɪl'],
    'would':  ['wəd', 'wʊd'],
    'should': ['ʃəd', 'ʃʊd'],
    'could':  ['kəd', 'kʊd'],
    'have':   ['həv', 'hæv'],
    'has':    ['həz', 'hæz'],
    'had':    ['həd', 'hæd'],
    'do':     ['də', 'du'],
    'does':   ['dəz', 'dʌz'],
    'did':    ['dɪd'],
    'been':   ['bɪn', 'bin'],
    'than':   ['ðən', 'ðæn'],
    'that':   ['ðət', 'ðæt'],
    'with':   ['wɪð', 'wɪθ'],
}


# =============================================================================
# Brightness
# =============================================================================

def brightness(symbol: str) -> float:
    """Diphthongs use their primary vowel's brightness."""
    if symbol in DIPHTHONGS:
        return brightness(DIPHTHONGS[symbol].primary)
    v = VOWELS.get(symbol)
    if not v:
        return 0.5
    b = 1.0 - v.x / 250.0
    closeness = 1.0 - v.y / 300.0
    factor = 0.6 + 0.4 * closeness
    if b > 0.5:
        b = 0.5 + (b - 0.5) * factor
    else:
        b = 0.5 - (0.5 - b) * factor
    if v.rounded:
        b -= 0.18
    return max(0.0, min(1.0, b))


def brightness_label(symbol: str) -> str:
    b = brightness(symbol)
    if b >= 0.7:
        return 'bright'
    if b >= 0.4:
        return 'neutral'
    return 'dark'


def brightness_color(b: float) -> QColor:
    """Warm peach (bright) → cool blue (dark)."""
    if b >= 0.5:
        t = (b - 0.5) * 2
        r = int(106 + (216 - 106) * t)
        g = int(96 + (168 - 96) * t)
        bb = int(120 + (130 - 120) * t)
    else:
        t = b * 2
        r = int(60 + (106 - 60) * t)
        g = int(96 + (96 - 96) * t)
        bb = int(168 + (120 - 168) * t)
    return QColor(r, g, bb)




def _tts_speak(word: str, ipa_pron: str = '') -> None:
    """Speak *word* via system TTS, using *ipa_pron* where supported.

    Windows: writes SSML to a UTF-8 temp file and passes the path to
    PowerShell SAPI — this avoids every inline escaping problem with
    non-ASCII IPA characters.
    macOS: `say` (no IPA support; speaks the word).
    Linux: `espeak-ng` then `espeak` fallback.
    Non-blocking. Silently does nothing if TTS is unavailable.
    """
    try:
        if sys.platform == 'win32':
            safe_word = word.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if ipa_pron:
                # XML-escape the IPA string for the ph attribute
                safe_ipa = (ipa_pron
                            .replace('&', '&amp;')
                            .replace('"', '&quot;')
                            .replace('<', '&lt;')
                            .replace('>', '&gt;'))
                ssml = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<speak version="1.0" '
                    'xmlns="http://www.w3.org/2001/10/synthesis" '
                    'xml:lang="en-US">'
                    f'<phoneme alphabet="ipa" ph="{safe_ipa}">{safe_word}</phoneme>'
                    '</speak>'
                )
            else:
                ssml = (
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<speak version="1.0" '
                    'xmlns="http://www.w3.org/2001/10/synthesis" '
                    f'xml:lang="en-US">{safe_word}</speak>'
                )

            # Write to a temp file so PowerShell reads it cleanly — no
            # inline escaping of IPA/Unicode characters in the PS command.
            tmp = tempfile.NamedTemporaryFile(
                mode='w', suffix='.xml', delete=False, encoding='utf-8')
            tmp.write(ssml)
            tmp_path = tmp.name
            tmp.close()

            # Forward slashes work fine in PowerShell paths and avoid
            # backslash escaping inside the double-quoted PS string.
            ps_path = tmp_path.replace('\\', '/')
            ps_cmd = (
                'Add-Type -AssemblyName System.Speech; '
                '$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                f'$s.SpeakSsml([System.IO.File]::ReadAllText("{ps_path}")); '
                f'Remove-Item "{ps_path}"'
            )
            subprocess.Popen(
                ['powershell', '-WindowStyle', 'Hidden', '-Command', ps_cmd],
                creationflags=0x08000000,
            )

        elif sys.platform == 'darwin':
            subprocess.Popen(['say', word])

        else:
            subprocess.Popen(['espeak-ng', '-v', 'en', word])

    except (OSError, FileNotFoundError):
        try:
            subprocess.Popen(['espeak', '-v', 'en', word])
        except (OSError, FileNotFoundError):
            pass


@dataclass
class WordAnnotation:
    word: str
    word_lower: str
    block: int
    start: int       # char offset within block
    end: int
    abs_start: int   # absolute document position
    abs_end: int
    tip_type: str    # legato | vowel_glide | crash | r_toxicity | plosive | nasal | approx | fricative
    tip_text: str
    color: str       # underline hex
    bg_color: str    # background tint hex


# =============================================================================
# Tokenization & syllable extraction
# =============================================================================

WORD_RE = re.compile(r"[A-Za-z]+(?:['\u2019][A-Za-z]+)*|[0-9]+")

VOWEL_CHARS = ''.join(VOWELS.keys())
_vowel_re = re.compile(
    '|'.join(re.escape(d) for d in DIPHTHONGS) + f'|[{re.escape(VOWEL_CHARS)}]'
)


def find_syllable_vowels(text: str):
    """Return list of (symbol, start, end). Symbol may be a diphthong."""
    return [(m.group(), m.start(), m.end()) for m in _vowel_re.finditer(text)]



# =============================================================================
# Consonant classification & diction helpers
# =============================================================================

IPA_PLOSIVES     = {'p', 'b', 't', 'd', 'k', 'g', 'ʔ', 'tʃ', 'dʒ'}
IPA_NASALS       = {'m', 'n', 'ŋ'}
IPA_FRICATIVES   = {'f', 'v', 'θ', 'ð', 's', 'z', 'ʃ', 'ʒ', 'h'}
IPA_APPROXIMANTS = {'l', 'ɹ', 'r', 'w', 'j'}
IPA_ALL_CONS     = IPA_PLOSIVES | IPA_NASALS | IPA_FRICATIVES | IPA_APPROXIMANTS


def ipa_trailing_consonants(pron: str) -> list:
    """Consonant symbols that follow the last vowel in *pron*."""
    syls = find_syllable_vowels(pron)
    tail = pron[syls[-1][2]:] if syls else pron
    result, i = [], 0
    while i < len(tail):
        two = tail[i:i+2]
        if two in ('tʃ', 'dʒ'):
            result.append(two); i += 2
        elif tail[i] in IPA_ALL_CONS:
            result.append(tail[i]); i += 1
        else:
            i += 1
    return result


def ipa_leading_vowel(pron: str) -> Optional[str]:
    """First vowel symbol if *pron* starts with a vowel (after stress marks), else None."""
    stripped = pron.lstrip('ˈˌ')
    if stripped[:2] in DIPHTHONGS:
        return stripped[:2]
    if stripped and stripped[0] in VOWELS:
        return stripped[0]
    return None


def vowel_stress_info(pron: str, vowel_idx: int):
    """Return (is_stressed: bool, is_primary: bool) for the vowel at *vowel_idx*."""
    syls = find_syllable_vowels(pron)
    if not syls or vowel_idx >= len(syls):
        return True, False
    # No stress diacritics anywhere → treat as stressed (mono-syllable content word)
    if 'ˈ' not in pron and 'ˌ' not in pron:
        return True, len(syls) == 1
    _, s, _ = syls[vowel_idx]
    prev_end = syls[vowel_idx - 1][2] if vowel_idx > 0 else 0
    segment = pron[prev_end:s]
    primary = 'ˈ' in segment
    secondary = 'ˌ' in segment
    return (primary or secondary), primary


def consonant_release_tip(consonants: list) -> str:
    """Human-readable release tip for a list of IPA consonant symbols."""
    if not consonants:
        return ''
    plosives    = [c for c in consonants if c in IPA_PLOSIVES]
    nasals      = [c for c in consonants if c in IPA_NASALS]
    approx      = [c for c in consonants if c in IPA_APPROXIMANTS]
    fricatives  = [c for c in consonants if c in IPA_FRICATIVES]
    lines = []
    if plosives:
        s = ' '.join(f'/{c}/' for c in plosives)
        lines.append(f'Plosive exit ({s}) — snap off instantly. No shadow vowel after it.')
    if nasals:
        s = ' '.join(f'/{c}/' for c in nasals)
        lines.append(f'Nasal exit ({s}) — carries pitch; sustain through it before releasing.')
    if approx:
        s = ' '.join(f'/{c}/' for c in approx)
        lines.append(f'Approximant exit ({s}) — gentle release; no hard cutoff needed.')
    if fricatives:
        s = ' '.join(f'/{c}/' for c in fricatives)
        lines.append(f'Fricative exit ({s}) — control the airstream; brief sustain is possible.')
    return chr(10).join(lines)


# R-colored consonant (trailing)
IPA_RHOTIC = {'ɹ', 'r'}

# Unvoiced consonants (vocal cords open → air dump)
IPA_UNVOICED = {'p', 't', 'k', 'f', 's', 'ʃ', 'h', 'θ', 'tʃ'}

# Sibilants (mic-hostile)
IPA_SIBILANT = {'s', 'z', 'ʃ', 'ʒ', 'tʃ', 'dʒ'}

# Vowel-glide routing: which semi-vowel to insert before next vowel
_GLIDE_J = {'i','ɪ','e','ɛ','æ','eɪ','aɪ','ɔɪ','ɪə','eə'}
_GLIDE_W = {'u','ʊ','o','ɔ','oʊ','aʊ','ʊə'}


def ipa_ends_with_vowel(pron: str) -> Optional[str]:
    """Return the final vowel symbol if *pron* ends on a vowel (nothing after
    it but length/stress marks), else None."""
    syls = find_syllable_vowels(pron)
    if not syls:
        return None
    sym, _, end = syls[-1]
    tail = pron[end:].strip('ːˈˌ')
    return sym if not tail else None


def ipa_leading_consonant(pron: str) -> Optional[str]:
    """First consonant symbol if *pron* starts with a consonant."""
    s = pron.lstrip('ˈˌ')
    two = s[:2]
    if two in ('tʃ', 'dʒ'):
        return two
    if s and s[0] in IPA_ALL_CONS:
        return s[0]
    return None


def consonant_crash_tip(trailing: list, next_leading: str) -> Optional[str]:
    """Return a tip string if trailing[-1] + next_leading forms a crash, else None."""
    if not trailing:
        return None
    last = trailing[-1]
    if last == next_leading and last in IPA_PLOSIVES:
        return (f'Geminate /{last}/{next_leading}/ — hold the first stop; '
                f'release only once on the second. Never double-articulate.')
    if last in IPA_PLOSIVES and next_leading in IPA_NASALS:
        return (f'/{last}/ before /{next_leading}/ — elide the plosive '
                f'completely; let the nasal carry the transition.')
    if last in IPA_PLOSIVES and next_leading in IPA_PLOSIVES and last != next_leading:
        return (f'/{last}/ into /{next_leading}/ — hold through the boundary; '
                f'release only on the second plosive.')
    return None


# Background tint colors (annotation type → bg hex blended with #14181f at ~30%)
ANN_BG = {
    'legato':      '#3a3220',
    'vowel_glide': '#1e2e1e',
    'crash':       '#3a2820',
    'r_toxicity':  '#3a1e1e',
    'dark_l':      '#2a3040',
    'glottal':     '#2a2a40',
    'plosive':     '#3a2830',
    'nasal':       '#1a2e28',
    'approx':      '#1a2838',
    'fricative':   '#281a36',
}
# Foreground underline colors
ANN_COLOR = {
    'legato':      '#c8a060',
    'vowel_glide': '#90c878',
    'crash':       '#d08060',
    'r_toxicity':  '#e05050',
    'dark_l':      '#8898c8',
    'glottal':     '#a888c8',
    'plosive':     '#c06878',
    'nasal':       '#78b8a0',
    'approx':      '#7898d0',
    'fricative':   '#9878b0',
}


def dedupe_pronunciations(items):
    seen, out = set(), []
    for s in items:
        key = s.replace('ˈ', '').replace('ˌ', '')
        if key and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def get_pronunciations(word: str, custom_ipa: Optional[dict] = None):
    word_l = word.lower()
    if custom_ipa and word_l in custom_ipa:
        # Strip surrounding slashes in case the user stored them (e.g. /valʒɑ̃/)
        return [custom_ipa[word_l].strip('/')]
    if word_l in FUNCTION_WORDS:
        return FUNCTION_WORDS[word_l].copy()

    raw = ipa.convert(word_l, retrieve_all=True) or []
    cleaned = [p for p in raw if p and '*' not in p]

    if not cleaned and ("'" in word_l or '\u2019' in word_l):
        stripped = word_l.replace("'", '').replace('\u2019', '')
        raw = ipa.convert(stripped, retrieve_all=True) or []
        cleaned = [p for p in raw if p and '*' not in p]

    return dedupe_pronunciations(cleaned)


def pronunciation_brightness(p: str) -> float:
    items = find_syllable_vowels(p)
    if not items:
        return 0.5
    return sum(brightness(s) for s, _, _ in items) / len(items)


def label_alternatives(items):
    if len(items) <= 1:
        return [(p, '') for p in items]
    scored = [(p, pronunciation_brightness(p)) for p in items]
    bmax = max(s for _, s in scored)
    bmin = min(s for _, s in scored)
    if bmax - bmin < 0.10:
        return [(p, '') for p, _ in scored]
    out = []
    for p, s in scored:
        if s >= bmax - 0.02:
            out.append((p, 'brighter'))
        elif s <= bmin + 0.02:
            out.append((p, 'darker'))
        else:
            out.append((p, ''))
    return out


# =============================================================================
# IPA HTML rendering — keeps stress markers, highlights vowels
# =============================================================================

COLOR_VOWEL = '#7898d0'
COLOR_STRESS = '#687890'


def render_ipa_html(p: str, highlight_token: Optional[str] = None,
                    highlight_index: int = -1) -> str:
    items = find_syllable_vowels(p)
    parts = ['/']
    last = 0
    for idx, (sym, s, e) in enumerate(items):
        pre = p[last:s]
        for ch in pre:
            if ch in ('ˈ', 'ˌ'):
                parts.append(
                    f'<span style="color:{COLOR_STRESS};'
                    f'font-weight:bold">{ch}</span>')
            else:
                parts.append(html.escape(ch))
        is_selected = (sym == highlight_token and idx == highlight_index)
        if is_selected:
            parts.append(
                f'<span style="color:#1c2230;background-color:{COLOR_VOWEL};'
                f'font-weight:bold;padding:0 4px;border-radius:3px">'
                f'{html.escape(sym)}</span>')
        else:
            parts.append(
                f'<span style="color:{COLOR_VOWEL};font-weight:bold">'
                f'{html.escape(sym)}</span>')
        last = e
    parts.append(html.escape(p[last:]))
    parts.append('/')
    return ''.join(parts)


# =============================================================================
# SVG chart
# =============================================================================

def create_vowel_chart_svg(highlight: Optional[str] = None) -> str:
    dwg = svgwrite.Drawing(
        profile='full', size=('100%', '100%'),
        viewBox='-65 -70 390 425',
        preserveAspectRatio='xMidYMid meet')

    marker = dwg.marker(insert=(5, 3), size=(7, 6), orient='auto',
                        id='mod-arrow')
    marker.add(dwg.path(d='M0,0 L6,3 L0,6 z', fill='#a8c8e8'))
    dwg.defs.add(marker)

    marker2 = dwg.marker(insert=(5, 3), size=(7, 6), orient='auto',
                         id='glide-arrow')
    marker2.add(dwg.path(d='M0,0 L6,3 L0,6 z', fill='#d8dfe8'))
    dwg.defs.add(marker2)

    grad = dwg.linearGradient(start=(0, 0), end=(1, 0), id='bg-bright')
    grad.add_stop_color(0.0, '#d8a878', opacity=0.32)
    grad.add_stop_color(0.5, '#5a607a', opacity=0.15)
    grad.add_stop_color(1.0, '#4878a8', opacity=0.32)
    dwg.defs.add(grad)

    dwg.add(dwg.polygon(points=[(0, 0), (250, 0), (250, 300), (50, 300)],
                        fill='url(#bg-bright)',
                        stroke='#5a6478', stroke_width=1.5))

    for s, e in [((17, 100), (250, 100)),
                 ((34, 200), (250, 200)),
                 ((125, 0), (150, 300))]:
        dwg.add(dwg.line(start=s, end=e, stroke='#3a4258', stroke_width=0.6,
                         stroke_dasharray='2,3'))

    for sym, v in VOWELS.items():
        dx = 8 if v.rounded else -8
        dwg.add(dwg.text(sym, insert=(v.x + dx, v.y + 5),
                         text_anchor='middle',
                         font_family='Charis SIL, Doulos SIL, Calibri, serif',
                         font_size='14', fill='#b8c0d0'))

    for x, txt in [(25, 'front'), (137, 'central'), (250, 'back')]:
        dwg.add(dwg.text(txt, insert=(x, -28), text_anchor='middle',
                         font_size='11', fill='#7888a0',
                         font_family='Inter, Segoe UI, sans-serif',
                         letter_spacing='1'))
    for y, txt in [(0, 'close'), (150, 'mid'), (300, 'open')]:
        dwg.add(dwg.text(txt, insert=(-18, y + 4), text_anchor='end',
                         font_size='11', fill='#7888a0',
                         font_family='Inter, Segoe UI, sans-serif'))

    if highlight in DIPHTHONGS:
        d = DIPHTHONGS[highlight]
        if d.primary in VOWELS and d.glide in VOWELS:
            pv = VOWELS[d.primary]
            gv = VOWELS[d.glide]
            pdx = 8 if pv.rounded else -8
            gdx = 8 if gv.rounded else -8
            pcx, pcy = pv.x + pdx, pv.y
            gcx, gcy = gv.x + gdx, gv.y

            ddx, ddy = gcx - pcx, gcy - pcy
            dist = math.hypot(ddx, ddy)
            if dist > 0:
                sx = pcx + 20 * ddx / dist
                sy = pcy + 20 * ddy / dist
                ex = gcx - 12 * ddx / dist
                ey = gcy - 12 * ddy / dist
                mx, my = (sx + ex) / 2, (sy + ey) / 2
                perp_x, perp_y = -ddy / dist, ddx / dist
                cx_q, cy_q = mx + perp_x * 18, my + perp_y * 18
                dwg.add(dwg.path(
                    d=f'M {sx},{sy} Q {cx_q},{cy_q} {ex},{ey}',
                    fill='none', stroke='#d8dfe8', stroke_width=2.2,
                    opacity=0.85, marker_end='url(#glide-arrow)'))

            dwg.add(dwg.circle(center=(gcx, gcy), r=13,
                               fill='#1c2230', stroke='#d8dfe8',
                               stroke_width=1.8, opacity=0.85))
            dwg.add(dwg.text(d.glide, insert=(gcx, gcy + 5),
                             text_anchor='middle',
                             font_family='Charis SIL, Doulos SIL, serif',
                             font_size='14', fill='#d8dfe8'))

            dwg.add(dwg.circle(center=(pcx, pcy), r=20,
                               fill='#7898d0', stroke='#a8c8e8',
                               stroke_width=2))
            dwg.add(dwg.text(d.primary, insert=(pcx, pcy + 7),
                             text_anchor='middle',
                             font_family='Charis SIL, Doulos SIL, serif',
                             font_size='22', font_weight='bold',
                             fill='#1c2230'))

            label_x = (pcx + gcx) / 2
            label_y = max(pcy, gcy) + 30
            dwg.add(dwg.text('sustain → vanish',
                             insert=(label_x, label_y),
                             text_anchor='middle', font_size='9',
                             fill='#98a8c0',
                             font_family='Inter, sans-serif',
                             letter_spacing='1', font_style='italic'))

    elif highlight in VOWELS:
        v = VOWELS[highlight]
        dx = 8 if v.rounded else -8
        cx, cy = v.x + dx, v.y

        if v.mod_high and v.mod_high in VOWELS and v.mod_high != highlight:
            m = VOWELS[v.mod_high]
            mdx = 8 if m.rounded else -8
            tx, ty = m.x + mdx, m.y
            ddx, ddy = tx - cx, ty - cy
            dist = math.hypot(ddx, ddy)
            if dist > 0:
                sx = cx + 20 * ddx / dist
                sy = cy + 20 * ddy / dist
                ex = tx - 11 * ddx / dist
                ey = ty - 11 * ddy / dist
                dwg.add(dwg.line(start=(sx, sy), end=(ex, ey),
                                 stroke='#a8c8e8', stroke_width=2,
                                 stroke_dasharray='4,3', opacity=0.75,
                                 marker_end='url(#mod-arrow)'))
                dwg.add(dwg.circle(center=(tx, ty), r=12,
                                   fill='#1c2230', stroke='#a8c8e8',
                                   stroke_width=1.4, opacity=0.7))

        dwg.add(dwg.circle(center=(cx, cy), r=20,
                           fill='#7898d0', stroke='#a8c8e8', stroke_width=2))
        dwg.add(dwg.text(highlight, insert=(cx, cy + 7),
                         text_anchor='middle',
                         font_family='Charis SIL, Doulos SIL, serif',
                         font_size='22', font_weight='bold',
                         fill='#1c2230'))

    stream = StringIO()
    dwg.write(stream)
    return stream.getvalue()


# =============================================================================
# Save / load
# =============================================================================

@dataclass
class Song:
    name: str = 'New Song'
    lyrics: str = ''
    custom_ipa: dict = field(default_factory=dict)
    pron_choices: dict = field(default_factory=dict)  # word -> preferred pron index
    dismissed_tips: set = field(default_factory=set)  # words whose inline hint is dismissed

    def to_dict(self):
        return {'name': self.name, 'lyrics': self.lyrics,
                'custom_ipa': dict(self.custom_ipa),
                'pron_choices': dict(self.pron_choices),
                'dismissed_tips': list(self.dismissed_tips)}

    @classmethod
    def from_dict(cls, d):
        return cls(name=d.get('name', 'Untitled'),
                   lyrics=d.get('lyrics', ''),
                   custom_ipa=dict(d.get('custom_ipa', {})),
                   pron_choices=dict(d.get('pron_choices', {})),
                   dismissed_tips=set(d.get('dismissed_tips', [])))


class SongStore:
    def __init__(self, app_data_dir: str):
        self.dir = app_data_dir
        self.path = os.path.join(app_data_dir, 'songs.json')

    def load(self):
        if not os.path.exists(self.path):
            return [Song(name='Untitled')], 0
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            songs = [Song.from_dict(s) for s in data.get('songs', [])]
            active = max(0, min(data.get('active_index', 0),
                                max(0, len(songs) - 1)))
            return (songs or [Song(name='Untitled')]), active
        except (json.JSONDecodeError, IOError, KeyError):
            return [Song(name='Untitled')], 0

    def save(self, songs, active_index: int):
        try:
            os.makedirs(self.dir, exist_ok=True)
            data = {
                'songs': [s.to_dict() for s in songs],
                'active_index': active_index,
            }
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except (IOError, OSError) as e:
            print(f'Warning: failed to save songs: {e}', file=sys.stderr)


# =============================================================================
# QSS theme — built dynamically so px values scale with DPI
# =============================================================================

def build_style(dpr: float, font_scale: float = 1.0) -> str:
    """Return the full QSS stylesheet with px values scaled by dpr and
    font sizes additionally scaled by font_scale.
    """

    def px(n: float) -> str:
        return f'{max(1, round(n * dpr))}px'

    def fs(n: float) -> str:  # font size: dpr + ui font scale
        return f'{max(1, round(n * dpr * font_scale))}px'

    return f"""
QMainWindow, QWidget {{
    background-color: #14181f;
    color: #d8dfe8;
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: {fs(13)};
}}
QTextEdit, QPlainTextEdit {{
    background-color: #1c2230;
    border: {px(1)} solid #2c344a;
    border-radius: {px(6)};
    padding: {px(14)};
    selection-background-color: #7898d0;
    selection-color: #14181f;
    font-family: 'Charis SIL', 'Georgia', serif;
    font-size: {fs(17)};
}}
QScrollArea {{ background-color: transparent; border: none; }}
QPushButton {{
    background-color: #1c2230;
    border: {px(1)} solid #3a4258;
    border-radius: {px(4)};
    padding: {px(8)} {px(16)};
    color: #d8dfe8;
    font-size: {fs(13)};
}}
QPushButton:hover {{ background-color: #283044; border-color: #7898d0; }}
QPushButton:pressed {{ background-color: #344058; }}
QPushButton:disabled {{ color: #4a5670; border-color: #1c2230; }}

QPushButton[role="vowel"] {{
    background-color: #1c2230;
    border: {px(1)} solid #4a5670;
    border-radius: {px(24)};
    min-width: {px(48)}; max-width: {px(48)};
    min-height: {px(48)}; max-height: {px(48)};
    font-family: 'Charis SIL', 'Doulos SIL', serif;
    font-size: {fs(20)};
    font-weight: bold;
    padding: 0;
}}
QPushButton[role="vowel"]:hover {{ border-color: #a8c8e8; }}
QPushButton[role="vowel"]:checked {{
    background-color: #7898d0;
    color: #14181f;
    border-color: #a8c8e8;
}}

QPushButton[role="alt"] {{
    text-align: left;
    padding: {px(10)} {px(16)};
    background-color: #1c2230;
    border: {px(1)} solid #2c344a;
    border-left: {px(4)} solid #3a4258;
    border-radius: {px(4)};
    font-family: 'Charis SIL', 'Doulos SIL', serif;
    font-size: {fs(16)};
}}
QPushButton[role="alt"][tag="brighter"] {{ border-left-color: #d8a878; }}
QPushButton[role="alt"][tag="darker"]   {{ border-left-color: #4878a8; }}
QPushButton[role="alt"][selected="true"] {{
    background-color: #283044;
    border-color: #7898d0;
}}
QPushButton[role="alt"][selected="true"][tag="darker"] {{
    border-color: #4878a8;
}}

QLabel#WordLabel {{
    font-size: {fs(30)};
    font-weight: bold;
    color: #a8c8e8;
    font-family: 'Charis SIL', 'Georgia', serif;
}}
QLabel#IpaLabel {{
    font-size: {fs(26)};
    color: #d8dfe8;
    font-family: 'Charis SIL', 'Doulos SIL', serif;
    padding: {px(2)} 0;
}}
QLabel#PanelTitle {{
    color: #6878a0;
    font-size: {fs(11)};
    font-weight: bold;
    letter-spacing: {px(2)};
}}
QLabel#Caption {{
    color: #98a8c0;
    font-size: {fs(12)};
    font-style: italic;
}}
QFrame#ArticulationCard {{
    background-color: #1c2230;
    border: {px(1)} solid #2c344a;
    border-radius: {px(6)};
}}
QLabel#CardTitle {{
    color: #a8c8e8;
    font-size: {fs(17)};
    font-weight: bold;
    font-family: 'Charis SIL', serif;
}}
QLabel#CardLine {{ color: #98a8c0; font-size: {fs(14)}; }}
QLabel#CardNotes {{
    color: #c8d0dc;
    font-size: {fs(14)};
    font-style: italic;
    padding-top: {px(4)};
    line-height: 130%;
}}
QFrame#LadderStep {{
    background-color: #283044;
    border: {px(1)} solid #3a4258;
    border-radius: {px(5)};
}}
QFrame#LadderStep:hover {{ background-color: #344058; border-color: #7898d0; }}
QLabel#LadderSym {{
    font-family: 'Charis SIL', 'Doulos SIL', serif;
    font-size: {fs(26)};
    font-weight: bold;
    color: #a8c8e8;
    background: transparent;
    border: none;
}}
QLabel#LadderExample {{
    color: #98a8c0;
    font-size: {fs(12)};
    font-style: italic;
    background: transparent;
    border: none;
}}
QLabel#LadderArrow {{
    color: #4a5670;
    font-size: {fs(20)};
    min-width: {px(14)};
    max-width: {px(22)};
}}
QLabel#LadderAxis {{
    color: #4a5670;
    font-size: {fs(11)};
    font-style: italic;
    letter-spacing: {px(1)};
    padding-top: {px(4)};
}}
QComboBox {{
    background-color: #1c2230;
    border: {px(1)} solid #3a4258;
    border-radius: {px(4)};
    padding: {px(6)} {px(10)};
    color: #d8dfe8;
    min-width: {px(200)};
    font-size: {fs(14)};
    font-family: 'Charis SIL', 'Georgia', serif;
    font-weight: bold;
}}
QComboBox:hover {{ border-color: #7898d0; }}
QComboBox QAbstractItemView {{
    background-color: #1c2230;
    border: {px(1)} solid #3a4258;
    color: #d8dfe8;
    selection-background-color: #283044;
    selection-color: #a8c8e8;
    padding: {px(4)};
}}
QComboBox::drop-down {{ border: none; width: {px(24)}; }}
QComboBox::down-arrow {{
    image: none;
    border-left: {px(4)} solid transparent;
    border-right: {px(4)} solid transparent;
    border-top: {px(6)} solid #7898d0;
    margin-right: {px(8)};
}}
QLineEdit {{
    background-color: #1c2230;
    border: {px(1)} solid #3a4258;
    border-radius: {px(4)};
    padding: {px(6)} {px(10)};
    color: #d8dfe8;
    font-size: {fs(14)};
    selection-background-color: #7898d0;
    selection-color: #14181f;
}}
QLineEdit:focus {{ border-color: #7898d0; }}
QSplitter::handle {{ background-color: #1c2230; width: {px(1)}; }}
QMenuBar {{ background-color: #14181f; color: #98a8c0; font-size: {fs(13)}; }}
QMenuBar::item:selected {{ background-color: #283044; }}
QMenu {{
    background-color: #1c2230;
    border: {px(1)} solid #2c344a;
    color: #d8dfe8;
    font-size: {fs(13)};
}}
QMenu::item {{ padding: {px(7)} {px(24)}; }}
QMenu::item:selected {{ background-color: #283044; }}
QMenu::separator {{ height: {px(1)}; background-color: #2c344a; margin: {px(4)} 0; }}
QScrollBar:vertical {{ background: #14181f; width: {px(10)}; border: none; }}
QScrollBar::handle:vertical {{
    background: #283044; border-radius: {px(5)}; min-height: {px(30)};
}}
QScrollBar::handle:vertical:hover {{ background: #3a4258; }}
QScrollBar::add-line, QScrollBar::sub-line {{ background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QDialog {{ background-color: #14181f; }}
QLabel#ChiaroscuroTip {{
    color: #a8a080;
    font-size: {fs(11)};
    font-style: italic;
    padding-top: {px(2)};
}}

QPushButton#HintsToggle, QToolButton#HintsToggle {{
    background-color: #1c2230;
    border: {px(1)} solid #3a4258;
    border-radius: {px(4)};
    padding: {px(4)} {px(10)};
    color: #6878a0;
    font-size: {fs(11)};
    font-weight: bold;
    letter-spacing: {px(1)};
}}
QPushButton#HintsToggle:hover, QToolButton#HintsToggle:hover {{ border-color: #c8a060; color: #c8a060; }}
QPushButton#HintsToggle:checked, QToolButton#HintsToggle:checked {{
    background-color: #201a0a;
    border-color: #c8a060;
    color: #c8a060;
}}

QLabel#LegatoTip {{
    color: #c8a060;
    background-color: #1e1a10;
    border: {px(1)} solid #4a3a18;
    border-left: {px(3)} solid #c8a060;
    border-radius: {px(4)};
    font-size: {fs(12)};
    padding: {px(6)} {px(10)};
    line-height: 140%;
}}
QLabel#ConsonantTip {{
    color: #8898b0;
    background-color: #161c28;
    border: {px(1)} solid #2a3248;
    border-left: {px(3)} solid #4a6090;
    border-radius: {px(4)};
    font-size: {fs(12)};
    padding: {px(6)} {px(10)};
    line-height: 140%;
}}
QLabel#StressWarning {{
    color: #c89060;
    background-color: #1e1810;
    border: {px(1)} solid #4a3818;
    border-left: {px(3)} solid #c89060;
    border-radius: {px(4)};
    font-size: {fs(12)};
    padding: {px(6)} {px(10)};
    line-height: 140%;
}}
"""


# =============================================================================
# Widgets
# =============================================================================

class AspectRatioContainer(QWidget):
    """Wraps a child widget and letterboxes it to preserve a target aspect."""
    def __init__(self, child: QWidget, ratio: float):
        super().__init__()
        self._child = child
        self._ratio = ratio
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(child)
        child.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def resizeEvent(self, ev):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            super().resizeEvent(ev)
            return
        target_w_for_h = h * self._ratio
        if target_w_for_h <= w:
            margin = int((w - target_w_for_h) / 2)
            self.layout().setContentsMargins(margin, 0, margin, 0)
        else:
            target_h_for_w = w / self._ratio
            margin = int((h - target_h_for_w) / 2)
            self.layout().setContentsMargins(0, margin, 0, margin)
        super().resizeEvent(ev)


class LyricsEditor(QTextEdit):
    word_clicked = pyqtSignal(str, int)
    word_ipa_requested = pyqtSignal(str)
    content_changed = pyqtSignal()
    annotation_dismissed = pyqtSignal(str)   # word_lower

    def __init__(self):
        super().__init__()
        self._annotation_map = {}   # (block, start, end) -> WordAnnotation
        self.setMouseTracking(True)
        self.setPlaceholderText(
            "Paste lyrics here. Click any word to see its IPA, vowel chart, "
            "and singing tips.\n\n"
            "Right-click any word to set a custom IPA (useful for proper "
            "nouns like \"Valjean\" or prisoner numbers like \"24601\")."
        )
        self.textChanged.connect(self.content_changed.emit)

    def _word_at_cursor_pos(self, pos):
        cursor = self.cursorForPosition(pos)
        block = cursor.block()
        pos_in_block = cursor.positionInBlock()
        for m in WORD_RE.finditer(block.text()):
            if m.start() <= pos_in_block <= m.end():
                return m.group(), block.blockNumber()
        return None, -1


    def set_annotations(self, annotations: list):
        """Apply background-tint + underline for all word annotations.
        Background tint is the primary visual signal on dark backgrounds.
        """
        self._annotation_map = {
            (a.block, a.start, a.end): a for a in annotations
        }
        selections = []
        for a in annotations:
            cur = QTextCursor(self.document())
            cur.setPosition(a.abs_start)
            cur.setPosition(a.abs_end, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(a.bg_color))
            fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
            fmt.setUnderlineColor(QColor(a.color))
            sel = QTextEdit.ExtraSelection()
            sel.cursor = cur
            sel.format = fmt
            selections.append(sel)
        self.setExtraSelections(selections)

    def clear_annotations(self):
        self._annotation_map = {}
        self.setExtraSelections([])

    def _annotation_at_pos(self, pos):
        cur = self.cursorForPosition(pos)
        bn = cur.block().blockNumber()
        pip = cur.positionInBlock()
        for (b, s, e), ann in self._annotation_map.items():
            if b == bn and s <= pip <= e:
                return ann
        return None

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        ann = self._annotation_at_pos(event.pos())
        if ann:
            QToolTip.showText(event.globalPos(), ann.tip_text, self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            word, bn = self._word_at_cursor_pos(event.pos())
            if word:
                self.word_clicked.emit(word.lower(), bn)

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu()
        word, _ = self._word_at_cursor_pos(event.pos())
        ann = self._annotation_at_pos(event.pos())
        if word:
            menu.addSeparator()
            action = menu.addAction(f'Set custom IPA for "{word}"…')
            action.triggered.connect(
                lambda _, w=word: self.word_ipa_requested.emit(w.lower()))
        if ann:
            da = menu.addAction(f'Dismiss hint for "{ann.word}"')
            da.triggered.connect(
                lambda _, w=ann.word_lower: self.annotation_dismissed.emit(w))
        menu.exec_(event.globalPos())

    def line_text(self, block_number: int) -> str:
        block = self.document().findBlockByNumber(block_number)
        return block.text() if block.isValid() else ''

    def insertFromMimeData(self, source):
        if source.hasText():
            text = source.text().replace('\r\n', '\n').replace('\r', '\n')
            self.insertPlainText(text)
        else:
            super().insertFromMimeData(source)


class VowelChartView(QWidget):
    def __init__(self):
        super().__init__()
        self._current = None
        self.setMinimumSize(_scale(280), _scale(320))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_QTSVG:
            self._view = QSvgWidget(self)
            self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self._view = QLabel(self)
            self._view.setAlignment(Qt.AlignCenter)
            self._view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._view)

        self.show_vowel(None)

    def show_vowel(self, sym):
        self._current = sym
        svg_str = create_vowel_chart_svg(sym)
        if HAS_QTSVG:
            self._view.load(svg_str.encode('utf-8'))
        else:
            size = min(self.width(), self.height()) or _scale(320)
            uri = 'data:image/svg+xml;base64,' + base64.b64encode(
                svg_str.encode()).decode()
            self._view.setText(f'<img src="{uri}" width="{size}">')

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not HAS_QTSVG:
            self.show_vowel(self._current)


class BrightnessBar(QWidget):
    """Horizontal bar showing where a vowel falls on the brightness spectrum."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(_scale(46))
        self._b = None

    def set_brightness(self, b):
        self._b = b
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        bar_left = 0
        bar_right = self.width()
        bar_top = _scale(4)
        bar_h = _scale(14)

        grad = QLinearGradient(bar_left, 0, bar_right, 0)
        grad.setColorAt(0.0, QColor('#4878a8'))
        grad.setColorAt(0.5, QColor('#5a607a'))
        grad.setColorAt(1.0, QColor('#d8a878'))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(bar_left, bar_top, bar_right - bar_left, bar_h,
                          _scale(7), _scale(7))

        p.setPen(QColor('#7888a0'))
        f = QFont('Inter', round(9 * _dpr()))
        p.setFont(f)
        label_y = bar_top + bar_h + _scale(4)
        label_h = _scale(18)
        p.drawText(bar_left, label_y, _scale(60), label_h,
                   Qt.AlignLeft | Qt.AlignTop, 'dark')
        p.drawText(bar_right - _scale(60), label_y, _scale(60), label_h,
                   Qt.AlignRight | Qt.AlignTop, 'bright')

        if self._b is not None:
            x = bar_left + int(self._b * (bar_right - bar_left))
            cy = bar_top + bar_h // 2
            r = _scale(7)
            p.setPen(QColor('#14181f'))
            p.setBrush(QColor('#d8dfe8'))
            p.drawEllipse(x - r, cy - r, r * 2, r * 2)


class LadderStep(QFrame):
    clicked = pyqtSignal(str)

    def __init__(self, sym: str):
        super().__init__()
        self.sym = sym
        self.setObjectName('LadderStep')
        self.setCursor(Qt.PointingHandCursor)

        sym_lbl = QLabel(sym)
        sym_lbl.setObjectName('LadderSym')
        sym_lbl.setAlignment(Qt.AlignCenter)

        ex = VOWEL_EXAMPLES.get(sym, '')
        ex_lbl = QLabel(ex if ex else '—')
        ex_lbl.setObjectName('LadderExample')
        ex_lbl.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_scale(10), _scale(6), _scale(10), _scale(6))
        layout.setSpacing(0)
        layout.addWidget(sym_lbl)
        layout.addWidget(ex_lbl)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self.sym)
        super().mousePressEvent(ev)


class ArticulationCard(QFrame):
    step_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName('ArticulationCard')
        self.setFrameShape(QFrame.StyledPanel)

        self.title = QLabel('Select a vowel above')
        self.title.setObjectName('CardTitle')
        self.title.setWordWrap(True)
        self.subtitle = QLabel('')
        self.subtitle.setObjectName('CardLine')
        self.subtitle.setWordWrap(True)
        self.tongue = QLabel('')
        self.tongue.setObjectName('CardLine')
        self.tongue.setWordWrap(True)
        self.lips = QLabel('')
        self.lips.setObjectName('CardLine')
        self.lips.setWordWrap(True)
        self.brightness_bar = BrightnessBar()
        self.notes = QLabel('')
        self.notes.setObjectName('CardNotes')
        self.notes.setWordWrap(True)

        self.stress_warning = QLabel('')
        self.stress_warning.setObjectName('StressWarning')
        self.stress_warning.setWordWrap(True)
        self.stress_warning.setVisible(False)

        self.section_header = QLabel('MODIFICATION AT HIGH PITCH')
        self.section_header.setObjectName('PanelTitle')
        self.section_caption = QLabel('')
        self.section_caption.setObjectName('Caption')
        self.section_caption.setWordWrap(True)

        self.ladder_row = QHBoxLayout()
        self.ladder_row.setSpacing(_scale(8))
        self.ladder_row.setContentsMargins(0, _scale(4), 0, 0)
        ladder_widget = QWidget()
        ladder_widget.setLayout(self.ladder_row)

        self.ladder_axis = QLabel('')
        self.ladder_axis.setObjectName('LadderAxis')
        self.ladder_axis.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(_scale(8))
        layout.setContentsMargins(_scale(16), _scale(16), _scale(16), _scale(16))
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.tongue)
        layout.addWidget(self.lips)
        layout.addWidget(self.brightness_bar)
        layout.addWidget(self.notes)
        layout.addWidget(self.stress_warning)
        layout.addSpacing(_scale(10))
        layout.addWidget(self.section_header)
        layout.addWidget(self.section_caption)
        layout.addWidget(ladder_widget)
        layout.addWidget(self.ladder_axis)

    def set_stress_warning(self, text: str):
        self.stress_warning.setText(text)
        self.stress_warning.setVisible(bool(text))

    def show_phone(self, sym):
        if sym in DIPHTHONGS:
            self._show_diphthong(sym)
        elif sym in VOWELS:
            self._show_vowel(sym)
        else:
            self._show_empty()

    def _show_empty(self):
        self.title.setText('Select a vowel above')
        self.subtitle.setText('')
        self.tongue.setText('')
        self.lips.setText('')
        self.notes.setText('')
        self.brightness_bar.set_brightness(None)
        self.set_stress_warning('')
        self.section_header.setText('')
        self.section_caption.setText('')
        self._clear_ladder()
        self.ladder_axis.setText('')

    def _show_vowel(self, sym):
        v = VOWELS[sym]
        example = VOWEL_EXAMPLES.get(sym, '')
        if example:
            self.title.setText(f'/{sym}/   ·   as in "{example}"')
        else:
            self.title.setText(f'/{sym}/')
        self.subtitle.setText(v.name)
        self.tongue.setText(
            f'Tongue: {v.tongue_height}, {v.tongue_advance}')
        self.lips.setText(f'Lips: {v.lips}')
        self.brightness_bar.set_brightness(brightness(sym))
        self.notes.setText(v.singing_note)

        self.section_header.setText('MODIFICATION AT HIGH PITCH')
        if v.mod_high and v.mod_high in VOWELS:
            self.section_caption.setText(
                "As pitch rises, this vowel relaxes toward the target on the "
                "right. Click either step to hear it.")
            self._build_ladder([sym, v.mod_high])
            self.ladder_axis.setText(
                '← comfortable pitch        ·        higher pitch →')
        else:
            self.section_caption.setText(
                'Already neutral — usually no modification needed at high pitch.')
            self._clear_ladder()
            step = LadderStep(sym)
            step.clicked.connect(self.step_clicked.emit)
            self.ladder_row.addWidget(step)
            self.ladder_row.addStretch()
            self.ladder_axis.setText('')

    def _show_diphthong(self, sym):
        d = DIPHTHONGS[sym]
        self.title.setText(f'/{sym}/   ·   {d.name} (as in {d.example})')
        self.subtitle.setText(
            f'A diphthong: glides from /{d.primary}/ to /{d.glide}/')
        if d.primary in VOWELS:
            pv = VOWELS[d.primary]
            self.tongue.setText(
                f'Primary /{d.primary}/ — tongue: {pv.tongue_height}, '
                f'{pv.tongue_advance}')
            self.lips.setText(f'Primary /{d.primary}/ — lips: {pv.lips}')
            self.brightness_bar.set_brightness(brightness(d.primary))
        self.notes.setText(d.singing_note)

        self.section_header.setText('DIPHTHONG GLIDE')
        self.section_caption.setText(
            "Sustain on the primary vowel for almost the whole duration. "
            "Vanish to the glide only at the very end. Click either to hear it.")
        self._build_ladder([d.primary, d.glide], glide_labels=True)
        self.ladder_axis.setText(
            '← sustain (most of the note)        ·        vanish (final ms) →')

    def _clear_ladder(self):
        while self.ladder_row.count():
            item = self.ladder_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _build_ladder(self, steps, glide_labels=False):
        self._clear_ladder()
        for i, s in enumerate(steps):
            if i > 0:
                arrow_char = '⇝' if glide_labels else '→'
                arrow = QLabel(arrow_char)
                arrow.setObjectName('LadderArrow')
                arrow.setAlignment(Qt.AlignCenter)
                self.ladder_row.addWidget(arrow)
            step = LadderStep(s)
            step.clicked.connect(self.step_clicked.emit)
            self.ladder_row.addWidget(step)
        self.ladder_row.addStretch()


class PhraseTrajectoryBar(QWidget):
    def __init__(self):
        super().__init__()
        h = _scale(72)
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)
        self._items = []  # (vowel_symbol, word_index)
        self._highlight_index = -1

    def set_phrase(self, items):
        self._items = list(items)
        self._highlight_index = -1
        self.update()

    def set_highlight(self, index: int):
        self._highlight_index = index
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(0, 0, -1, -1)
        p.setPen(QColor('#2c344a'))
        p.setBrush(QColor('#1c2230'))
        p.drawRoundedRect(rect, _scale(6), _scale(6))

        if not self._items:
            p.setPen(QColor('#4a5670'))
            f = QFont('Inter', round(11 * _dpr()))
            f.setItalic(True)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Click a word to see its line's vowel trajectory")
            return

        n = len(self._items)
        margin = _scale(10)
        usable_w = self.width() - 2 * margin
        word_gap = _scale(5)
        word_indices = [wi for _, wi in self._items]
        n_word_gaps = sum(1 for i in range(1, n)
                          if word_indices[i] != word_indices[i - 1])
        total_gap_w = word_gap * n_word_gaps
        cell_total_w = (usable_w - total_gap_w) / n if n > 0 else 0

        bar_top = _scale(10)
        bar_h = self.height() - _scale(20) - _scale(20)

        x = float(margin)
        for i, (vsym, wi) in enumerate(self._items):
            if i > 0 and word_indices[i] != word_indices[i - 1]:
                x += word_gap
            b = brightness(vsym)
            color = brightness_color(b)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            cell_x = int(x)
            cell_w = max(2, int(cell_total_w) - 2)
            p.drawRoundedRect(cell_x, bar_top, cell_w, bar_h, _scale(4), _scale(4))

            if i == self._highlight_index:
                p.setPen(QColor('#d8dfe8'))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(cell_x - 1, bar_top - 1,
                                  cell_w + 2, bar_h + 2, _scale(5), _scale(5))

            p.setPen(QColor('#d8dfe8'))
            f = QFont('Charis SIL', round(12 * _dpr()))
            p.setFont(f)
            p.drawText(cell_x, bar_top + bar_h + _scale(2),
                       cell_w, _scale(18), Qt.AlignCenter, vsym)

            x += cell_total_w


class AnalysisPanel(QWidget):
    play_requested = pyqtSignal(str)
    vowel_selected = pyqtSignal(int)
    pronunciation_chosen = pyqtSignal(str, int)  # (word, pron_index)

    def __init__(self):
        super().__init__()
        self._pronunciations = []
        self._current_pron_index = 0
        self._current_vowel = None
        self._current_word = ''
        self._current_syllables = []
        self._next_ipa = None

        word_header = QWidget()
        wh_layout = QHBoxLayout(word_header)
        wh_layout.setContentsMargins(0, 0, 0, 0)
        wh_layout.setSpacing(_scale(8))
        self.word_label = QLabel('Click a word to begin')
        self.word_label.setObjectName('WordLabel')
        self.speak_btn = QPushButton('▶ Speak')
        self.speak_btn.setFixedHeight(_scale(28))
        self.speak_btn.setEnabled(False)
        self.speak_btn.clicked.connect(self._on_speak)
        wh_layout.addWidget(self.word_label, 1)
        wh_layout.addWidget(self.speak_btn)

        self.ipa_label = QLabel('')
        self.ipa_label.setObjectName('IpaLabel')
        self.ipa_label.setTextFormat(Qt.RichText)
        self.ipa_label.setWordWrap(True)

        self.legato_tip = QLabel('')
        self.legato_tip.setObjectName('LegatoTip')
        self.legato_tip.setWordWrap(True)
        self.legato_tip.setVisible(False)

        self.consonant_tip = QLabel('')
        self.consonant_tip.setObjectName('ConsonantTip')
        self.consonant_tip.setWordWrap(True)
        self.consonant_tip.setVisible(False)

        alt_header = QLabel('PRONUNCIATIONS')
        alt_header.setObjectName('PanelTitle')
        self.alt_layout = QVBoxLayout()
        self.alt_layout.setSpacing(_scale(4))
        alt_wrap = QWidget()
        alt_wrap.setLayout(self.alt_layout)

        vowel_header = QLabel('SYLLABLE VOWELS')
        vowel_header.setObjectName('PanelTitle')
        self.vowel_btn_layout = QHBoxLayout()
        self.vowel_btn_layout.setSpacing(_scale(8))
        self.vowel_btn_layout.addStretch()
        vowel_btn_wrap = QWidget()
        vowel_btn_wrap.setLayout(self.vowel_btn_layout)

        self.chart = VowelChartView()
        chart_container = AspectRatioContainer(self.chart, 390 / 425)
        chart_container.setMinimumHeight(_scale(360))

        self.card = ArticulationCard()
        self.card.step_clicked.connect(self._set_current_vowel)

        self.play_btn = QPushButton('▶  Play vowel sound')
        self.play_btn.clicked.connect(self._on_play)
        self.play_btn.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_scale(20), _scale(20), _scale(20), _scale(20))
        layout.setSpacing(_scale(10))
        layout.addWidget(word_header)
        layout.addWidget(self.ipa_label)
        layout.addWidget(self.legato_tip)
        layout.addWidget(self.consonant_tip)
        layout.addSpacing(_scale(4))
        layout.addWidget(alt_header)
        layout.addWidget(alt_wrap)
        layout.addSpacing(_scale(4))
        layout.addWidget(vowel_header)
        layout.addWidget(vowel_btn_wrap)
        layout.addWidget(chart_container, 1)
        layout.addWidget(self.card)
        layout.addWidget(self.play_btn)

    def show_word(self, word, pronunciations, initial_index=0, next_ipa=None):
        self._pronunciations = pronunciations
        self._current_pron_index = 0
        self._current_word = word
        self._next_ipa = next_ipa
        self.word_label.setText(word)
        self.speak_btn.setEnabled(bool(word and word != 'Click a word to begin'))

        if not pronunciations:
            self.ipa_label.setText(
                '<span style="color:#6878a0;font-style:italic">'
                'No pronunciation found. Right-click the word in the lyrics '
                'to set a custom IPA.</span>')
            self._clear_alts()
            self._clear_vowel_buttons()
            self.chart.show_vowel(None)
            self.card.show_phone(None)
            self.play_btn.setEnabled(False)
            self.speak_btn.setEnabled(False)
            self.legato_tip.setVisible(False)
            self.consonant_tip.setVisible(False)
            return

        self._populate_alts(pronunciations)
        idx = initial_index if 0 <= initial_index < len(pronunciations) else 0
        self._select_pronunciation(idx)

    def _populate_alts(self, pronunciations):
        self._clear_alts()
        if len(pronunciations) <= 1:
            return
        labelled = label_alternatives(pronunciations)
        for i, (p, tag) in enumerate(labelled):
            display_p = render_ipa_html(p)
            text = display_p
            if tag:
                text = f'{display_p}   ·   {tag}'
            btn = QPushButton()
            btn.setText('')
            btn.setProperty('role', 'alt')
            if tag:
                btn.setProperty('tag', tag)
            btn.setProperty('selected', 'false')
            inner = QLabel(text)
            inner.setTextFormat(Qt.RichText)
            inner.setStyleSheet('background: transparent; color: #d8dfe8;')
            inner.setAttribute(Qt.WA_TransparentForMouseEvents)
            inner_l = QHBoxLayout(btn)
            inner_l.setContentsMargins(_scale(14), _scale(8), _scale(14), _scale(8))
            inner_l.addWidget(inner)
            btn.clicked.connect(
                lambda _, idx=i: self._select_pronunciation(idx))
            self.alt_layout.addWidget(btn)

    def _select_pronunciation(self, idx):
        if idx < 0 or idx >= len(self._pronunciations):
            return
        self._current_pron_index = idx
        p = self._pronunciations[idx]
        self.pronunciation_chosen.emit(self._current_word, idx)
        self._update_word_tips(p)

        for i in range(self.alt_layout.count()):
            w = self.alt_layout.itemAt(i).widget()
            if w is None:
                continue
            w.setProperty('selected', 'true' if i == idx else 'false')
            w.style().unpolish(w)
            w.style().polish(w)

        self._current_syllables = find_syllable_vowels(p)
        first_sym = self._current_syllables[0][0] if self._current_syllables else None
        self._render_ipa(p, first_sym, 0)
        self._populate_vowel_buttons(self._current_syllables)
        self._set_current_vowel(first_sym, 0 if first_sym else None)

    def _render_ipa(self, p, highlight_sym, highlight_idx):
        if highlight_sym is None:
            self.ipa_label.setText('/' + html.escape(p) + '/')
        else:
            self.ipa_label.setText(
                render_ipa_html(p, highlight_sym, highlight_idx))

    def _populate_vowel_buttons(self, syllables):
        self._clear_vowel_buttons()
        for idx, (sym, _, _) in enumerate(syllables):
            btn = QPushButton(sym)
            btn.setProperty('role', 'vowel')
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda _, s=sym, i=idx: self._set_current_vowel(s, i))
            self.vowel_btn_layout.insertWidget(
                self.vowel_btn_layout.count() - 1, btn)

    def _set_current_vowel(self, sym, index=None):
        if index is None and sym is not None:
            for i, (s, _, _) in enumerate(self._current_syllables):
                if s == sym:
                    index = i
                    break
        self._current_vowel = sym
        self.chart.show_vowel(sym)
        self.card.show_phone(sym)
        self.play_btn.setEnabled(sym is not None)

        for i in range(self.vowel_btn_layout.count()):
            w = self.vowel_btn_layout.itemAt(i).widget()
            if isinstance(w, QPushButton):
                w.setChecked(w.text() == sym)

        if self._pronunciations and self._current_pron_index < len(self._pronunciations):
            self._render_ipa(
                self._pronunciations[self._current_pron_index], sym,
                index if index is not None else -1)

        self._update_stress_warning(index)
        if index is not None and index >= 0:
            self.vowel_selected.emit(index)

    def _update_word_tips(self, pron: str):
        """Refresh the panel tips using the same priority logic as inline annotations,
        so the text in the panel matches the hover tooltip on the word.
        """
        trailing  = ipa_trailing_consonants(pron)
        end_vowel = ipa_ends_with_vowel(pron)
        next_ipa  = self._next_ipa

        next_leading_v = ipa_leading_vowel(next_ipa) if next_ipa else None
        next_leading_c = ipa_leading_consonant(next_ipa) if next_ipa else None
        rhotics   = [c for c in trailing if c in IPA_RHOTIC]
        has_rhotic_vowel = any(s in ('ɚ', 'ɝ') for s, _, _ in find_syllable_vowels(pron))

        legato_text = cons_text = ''

        # Priority mirrors _compute_annotations exactly
        if trailing and next_leading_v is not None:
            cd = ' '.join(f'/{c}/' for c in trailing)
            legato_text = (f'\u2197 Legato \u2014 carry {cd} into /{next_leading_v}/ '
                           f'of the next word. Keep the breath connected.')
        elif end_vowel is not None and next_leading_v is not None:
            glide = '/j/' if end_vowel in _GLIDE_J else '/w/'
            legato_text = (f'Vowel-to-vowel \u2014 insert {glide} to avoid '
                           f'a glottal stop before /{next_leading_v}/. Keep airflow open.')
        elif trailing and next_leading_c is not None:
            crash = consonant_crash_tip(trailing, next_leading_c)
            if crash:
                legato_text = crash

        # Consonant / rhotic tip (secondary)
        if rhotics or has_rhotic_vowel:
            cons_text = ('American R \u2014 de-rhotacize: release the tongue curl/bunch. '
                         'Sustain on \u0259 or \u025c instead.')
        elif trailing:
            cons_text = consonant_release_tip(trailing)

        self.legato_tip.setText(legato_text)
        self.legato_tip.setVisible(bool(legato_text))
        self.consonant_tip.setText(cons_text)
        self.consonant_tip.setVisible(bool(cons_text))

    def _update_stress_warning(self, vowel_idx):
        """Refresh stress warning (feature 3) for the currently selected vowel."""
        if vowel_idx is None or not self._pronunciations:
            self.card.set_stress_warning('')
            return
        pron = (self._pronunciations[self._current_pron_index]
                if self._current_pron_index < len(self._pronunciations) else '')
        if not pron:
            self.card.set_stress_warning('')
            return
        stressed, _ = vowel_stress_info(pron, vowel_idx)
        if not stressed:
            sym = self._current_vowel or ''
            if sym in ('ə', 'ɪ', 'ɚ', 'ɘ'):
                self.card.set_stress_warning(
                    '⚠  Unstressed weak vowel — resist coloring or weighting '
                    'this syllable. Keep it light and neutral; any deliberate '
                    'shaping here will distort the natural speech rhythm.')
            else:
                self.card.set_stress_warning(
                    '⚠  Unstressed syllable — the stress falls elsewhere in '
                    'this word. Don’t over-sing this vowel; let it stay '
                    'subordinate to the stressed syllable.')
        else:
            self.card.set_stress_warning('')

    def _clear_alts(self):
        while self.alt_layout.count():
            item = self.alt_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_vowel_buttons(self):
        while self.vowel_btn_layout.count() > 1:
            item = self.vowel_btn_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_speak(self):
        if not self._current_word or self._current_word == 'Click a word to begin':
            return
        # Use the currently selected pronunciation so Valjean etc. are correct
        ipa_pron = ''
        if self._pronunciations and self._current_pron_index < len(self._pronunciations):
            ipa_pron = self._pronunciations[self._current_pron_index]
        # Strip surrounding slashes in case the user stored the IPA with them
        ipa_pron = ipa_pron.strip('/')
        _tts_speak(self._current_word, ipa_pron)

    def _on_play(self):
        if self._current_vowel:
            self.play_requested.emit(self._current_vowel)


class CustomIpaDialog(QDialog):
    def __init__(self, word, current_ipa, default_ipas, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Custom IPA')
        self.setMinimumWidth(_scale(460))

        info = QLabel(
            f'Set IPA for <b style="color:#a8c8e8">"{html.escape(word)}"</b>.<br>'
            f'<span style="color:#98a8c0;font-size:11px;font-style:italic">'
            f'Use IPA characters directly. Copy from the chart if needed.'
            f'</span>')
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)

        if default_ipas:
            default_text = (
                f'<span style="color:#98a8c0">Dictionary form: '
                f'<span style="color:#7898d0">/{"/  /".join(default_ipas)}/</span>'
                f'</span>')
        else:
            default_text = (
                '<span style="color:#98a8c0">'
                'No dictionary pronunciation available for this word.</span>')
        default = QLabel(default_text)
        default.setTextFormat(Qt.RichText)
        default.setWordWrap(True)

        self.edit = QLineEdit()
        f = QFont('Charis SIL', round(14 * _dpr()))
        self.edit.setFont(f)
        self.edit.setText(current_ipa or '')
        self.edit.setPlaceholderText('e.g. valʒɑ̃')

        cheat = QLabel(
            '<span style="color:#6878a0;font-size:11px">'
            'Quick reference: ə ɛ æ ɑ ɔ ʌ ʊ ɪ ʃ ʒ ð θ ŋ ɹ ɚ ɝ • diphthongs eɪ aɪ aʊ oʊ ɔɪ'
            '</span>')
        cheat.setTextFormat(Qt.RichText)
        cheat.setWordWrap(True)

        btns = QDialogButtonBox()
        self.reset_btn = btns.addButton('Clear override',
                                        QDialogButtonBox.DestructiveRole)
        btns.addButton(QDialogButtonBox.Cancel)
        self.save_btn = btns.addButton(QDialogButtonBox.Save)
        self.save_btn.clicked.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.reset_btn.clicked.connect(self._on_reset)
        self._reset_clicked = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_scale(20), _scale(20), _scale(20), _scale(16))
        layout.setSpacing(_scale(10))
        layout.addWidget(info)
        layout.addWidget(default)
        layout.addWidget(self.edit)
        layout.addWidget(cheat)
        layout.addSpacing(_scale(4))
        layout.addWidget(btns)

    def _on_reset(self):
        self._reset_clicked = True
        self.accept()

    def result_ipa(self):
        if self._reset_clicked:
            return ''
        return self.edit.text().strip().strip('/')


class SongSelectorBar(QWidget):
    song_changed = pyqtSignal(int)
    new_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.combo = QComboBox()
        self.combo.currentIndexChanged.connect(self.song_changed.emit)
        new_btn = QPushButton('+  New')
        new_btn.clicked.connect(self.new_requested.emit)
        rename_btn = QPushButton('Rename')
        rename_btn.clicked.connect(self.rename_requested.emit)
        del_btn = QPushButton('Delete')
        del_btn.clicked.connect(self.delete_requested.emit)

        title = QLabel('SONG')
        title.setObjectName('PanelTitle')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_scale(8))
        layout.addWidget(title)
        layout.addWidget(self.combo, 1)
        layout.addWidget(new_btn)
        layout.addWidget(rename_btn)
        layout.addWidget(del_btn)

    def refresh(self, songs, active_index):
        self.combo.blockSignals(True)
        self.combo.clear()
        for s in songs:
            self.combo.addItem(s.name)
        if 0 <= active_index < self.combo.count():
            self.combo.setCurrentIndex(active_index)
        self.combo.blockSignals(False)


class BulkImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Bulk Import Custom IPAs')
        self.setMinimumSize(_scale(560), _scale(380))

        info = QLabel(
            'Paste a JSON object mapping words to IPA. Existing overrides for '
            'the same words will be replaced; others stay as-is.<br>'
            '<span style="color:#98a8c0;font-style:italic;font-size:11px">'
            'Example: <code>{"valjean": "valʒɑ̃", "cosette": "kɔzɛt"}</code>'
            '</span>')
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)

        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText('{\n  "valjean": "valʒɑ̃",\n  "cosette": "kɔzɛt"\n}')

        btns = QDialogButtonBox(
            QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        btns.button(QDialogButtonBox.Apply).clicked.connect(self.accept)
        btns.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(info)
        layout.addWidget(self.edit)
        layout.addWidget(btns)

    def parsed(self):
        try:
            text = self.edit.toPlainText().strip()
            if not text:
                return {}
            data = json.loads(text)
            if not isinstance(data, dict):
                return None
            return {str(k).lower(): str(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError):
            return None


# =============================================================================
# Main window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings('Heng', 'LyricIPAFinder')
        self.player = QMediaPlayer()

        app_data = QStandardPaths.writableLocation(
            QStandardPaths.AppLocalDataLocation)
        if not app_data:
            app_data = os.path.expanduser('~/.lyric_ipa_finder')
        self.store = SongStore(app_data)
        self.songs, self.active_index = self.store.load()

        self._pron_cache = {}
        self._pron_index_cache = {}  # word -> preferred pronunciation index
        self._current_block_number = -1
        self._current_line_items = []
        self._current_clicked_word_idx = -1
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._persist_songs)

        self._editor_font_size = 16
        self._ui_font_scale = 1.0
        self._annotations_enabled = True
        self._enabled_hint_types = {'legato','vowel_glide','crash','r_toxicity','dark_l','glottal','plosive','nasal','approx','fricative'}
        self._word_annotations = []
        self._annotation_timer = QTimer(self)
        self._annotation_timer.setSingleShot(True)
        self._annotation_timer.setInterval(900)
        self._annotation_timer.timeout.connect(self._compute_annotations)

        self._init_ui()
        self._restore_state()
        self._load_active_song()

    def _init_ui(self):
        self.setWindowTitle('Lyric IPA Finder')
        self.setStyleSheet(build_style(_dpr(), self._ui_font_scale))

        self.song_bar = SongSelectorBar()
        self.song_bar.song_changed.connect(self._on_song_changed)
        self.song_bar.new_requested.connect(self._on_new_song)
        self.song_bar.rename_requested.connect(self._on_rename_song)
        self.song_bar.delete_requested.connect(self._on_delete_song)

        self.editor = LyricsEditor()
        self._apply_editor_font()
        self.editor.word_clicked.connect(self._on_word_clicked)
        self.editor.word_ipa_requested.connect(self._on_word_ipa_requested)
        self.editor.content_changed.connect(self._on_lyrics_changed)
        self.editor.annotation_dismissed.connect(self._on_annotation_dismissed)

        editor_container = QWidget()
        ec_layout = QVBoxLayout(editor_container)
        ec_layout.setContentsMargins(_scale(20), _scale(16), _scale(12), _scale(20))
        ec_layout.setSpacing(_scale(8))

        ec_layout.addWidget(self.song_bar)
        ec_layout.addSpacing(_scale(4))

        lyrics_header = QWidget()
        lh_layout = QHBoxLayout(lyrics_header)
        lh_layout.setContentsMargins(0, 0, 0, 0)
        lh_layout.setSpacing(_scale(8))
        lyrics_title = QLabel('LYRICS')
        lyrics_title.setObjectName('PanelTitle')
        self.hints_btn = QToolButton()
        self.hints_btn.setObjectName('HintsToggle')
        self.hints_btn.setFixedHeight(_scale(22))
        self.hints_btn.setPopupMode(QToolButton.InstantPopup)
        self.hints_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._hints_menu = self._build_hints_menu()
        self.hints_btn.setMenu(self._hints_menu)
        self._update_hints_btn_label()
        lh_layout.addWidget(lyrics_title)
        lh_layout.addStretch()
        lh_layout.addWidget(self.hints_btn)
        ec_layout.addWidget(lyrics_header)
        ec_layout.addWidget(self.editor, 1)

        traj_title = QLabel('PHRASE TRAJECTORY')
        traj_title.setObjectName('PanelTitle')
        traj_caption = QLabel(
            "Each cell is one vowel from the current line, colored by "
            "brightness (warm = bright, cool = dark). Gaps separate words. "
            "Click a vowel in the analysis panel to spotlight where it sits "
            "in the phrase — useful for seeing the tone-color arc of the line "
            "and which vowels carry the line's color."
        )
        traj_caption.setObjectName('Caption')
        traj_caption.setWordWrap(True)
        self.trajectory = PhraseTrajectoryBar()
        ec_layout.addSpacing(_scale(4))
        ec_layout.addWidget(traj_title)
        ec_layout.addWidget(traj_caption)
        ec_layout.addWidget(self.trajectory)
        self.chiaroscuro_label = QLabel('')
        self.chiaroscuro_label.setObjectName('ChiaroscuroTip')
        self.chiaroscuro_label.setWordWrap(True)
        self.chiaroscuro_label.setVisible(False)
        ec_layout.addWidget(self.chiaroscuro_label)
        self.breath_label = QLabel('')
        self.breath_label.setObjectName('ChiaroscuroTip')
        self.breath_label.setWordWrap(True)
        self.breath_label.setVisible(False)
        ec_layout.addWidget(self.breath_label)
        self.sibilance_label = QLabel('')
        self.sibilance_label.setObjectName('ChiaroscuroTip')
        self.sibilance_label.setWordWrap(True)
        self.sibilance_label.setVisible(False)
        ec_layout.addWidget(self.sibilance_label)

        self.analysis = AnalysisPanel()
        self.analysis.play_requested.connect(self._play_vowel)
        self.analysis.vowel_selected.connect(self._on_vowel_selected_in_analysis)
        self.analysis.pronunciation_chosen.connect(self._on_pronunciation_chosen)

        analysis_scroll = QScrollArea()
        analysis_scroll.setWidgetResizable(True)
        analysis_scroll.setFrameShape(QFrame.NoFrame)
        analysis_scroll.setWidget(self.analysis)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(editor_container)
        splitter.addWidget(analysis_scroll)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([_scale(640), _scale(640)])
        self.setCentralWidget(splitter)

        self._setup_menu()
        self.resize(_scale(1320), _scale(880))

    def _setup_menu(self):
        s = self.menuBar().addMenu('&Song')
        a = QAction('&Bulk Import IPAs…', self)
        a.triggered.connect(self._on_bulk_import)
        s.addAction(a)
        a = QAction('&Generate IPA Prompt to Clipboard', self)
        a.triggered.connect(self._on_generate_prompt)
        s.addAction(a)
        s.addSeparator()
        a = QAction('Reset Dismissed Hints', self)
        a.triggered.connect(self._on_reset_dismissed_hints)
        s.addAction(a)
        s.addSeparator()
        a = QAction('Open Save Folder', self)
        a.triggered.connect(self._on_open_save_folder)
        s.addAction(a)

        s = self.menuBar().addMenu('&View')
        a = QAction('&Adjust Lyrics Font Size…', self)
        a.triggered.connect(self._adjust_font_size)
        s.addAction(a)
        a = QAction('Adjust &UI Scale…', self)
        a.triggered.connect(self._adjust_ui_scale)
        s.addAction(a)

    def _apply_editor_font(self):
        """Set lyrics editor font via a widget-level stylesheet so it
        overrides the global QSS font-size rule reliably.
        Font family comes from the global QSS; only size is set here.
        """
        self.editor.setStyleSheet(
            f"QTextEdit {{ font-size: {self._editor_font_size}pt; }}"
        )

    def _adjust_ui_scale(self):
        """Let the user scale all UI text (labels, buttons, menus) as a
        percentage of the default size.
        """
        pct = round(self._ui_font_scale * 100)
        new_pct, ok = QInputDialog.getInt(
            self, 'UI Scale', 'UI font scale (%):',
            value=pct, min=75, max=200, step=25)
        if ok:
            self._ui_font_scale = new_pct / 100.0
            self.setStyleSheet(build_style(_dpr(), self._ui_font_scale))

    def _adjust_font_size(self):
        new, ok = QInputDialog.getInt(
            self, 'Adjust Font Size', 'Lyrics font size:',
            value=self._editor_font_size, min=8, max=40)
        if ok:
            self._editor_font_size = new
            self._apply_editor_font()

    # ---- Song handling ----

    @property
    def active_song(self):
        return self.songs[self.active_index]

    def _load_active_song(self):
        self.song_bar.refresh(self.songs, self.active_index)
        song = self.active_song
        self.editor.blockSignals(True)
        self.editor.setPlainText(song.lyrics)
        self.editor.blockSignals(False)
        self._pron_cache.clear()
        self._pron_index_cache = dict(song.pron_choices)
        self._annotation_timer.start()   # recompute hints after load
        self.analysis.show_word('Click a word to begin', [])
        self.trajectory.set_phrase([])
        self._current_line_items = []
        self._current_clicked_word_idx = -1
        self._current_block_number = -1

    def _on_song_changed(self, idx):
        if idx < 0 or idx >= len(self.songs) or idx == self.active_index:
            return
        self.active_song.lyrics = self.editor.toPlainText()
        self.active_index = idx
        self._load_active_song()
        self._schedule_save()

    def _on_new_song(self):
        name, ok = QInputDialog.getText(
            self, 'New Song', 'Name:', text='Untitled')
        if not ok or not name.strip():
            return
        self.active_song.lyrics = self.editor.toPlainText()
        self.songs.append(Song(name=name.strip()))
        self.active_index = len(self.songs) - 1
        self._load_active_song()
        self._schedule_save()

    def _on_rename_song(self):
        new, ok = QInputDialog.getText(
            self, 'Rename Song', 'Name:', text=self.active_song.name)
        if ok and new.strip():
            self.active_song.name = new.strip()
            self.song_bar.refresh(self.songs, self.active_index)
            self._schedule_save()

    def _on_delete_song(self):
        if len(self.songs) <= 1:
            QMessageBox.information(
                self, 'Cannot Delete',
                'At least one song must remain. Rename or replace this one instead.')
            return
        confirm = QMessageBox.question(
            self, 'Delete Song',
            f'Delete "{self.active_song.name}"? This cannot be undone.',
            QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        del self.songs[self.active_index]
        self.active_index = max(0, self.active_index - 1)
        self._load_active_song()
        self._schedule_save()

    def _on_lyrics_changed(self):
        self.active_song.lyrics = self.editor.toPlainText()
        self._schedule_save()
        self._annotation_timer.start()

    def _schedule_save(self):
        self._save_timer.start()

    def _persist_songs(self):
        self.store.save(self.songs, self.active_index)

    # ---- Custom IPA ----

    def _on_word_ipa_requested(self, word):
        word_l = word.lower()
        custom = self.active_song.custom_ipa
        current = custom.get(word_l, '')
        if word_l in FUNCTION_WORDS:
            defaults = FUNCTION_WORDS[word_l]
        else:
            raw = ipa.convert(word_l, retrieve_all=True) or []
            defaults = [p for p in raw if p and '*' not in p]
        dlg = CustomIpaDialog(word, current, defaults, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        new = dlg.result_ipa()
        if new is None:
            return
        if new == '':
            custom.pop(word_l, None)
        else:
            custom[word_l] = new
        self._pron_cache.pop(word_l, None)
        if self._current_block_number >= 0:
            line = self.editor.line_text(self._current_block_number)
            self._update_trajectory(line)
            if self.analysis.word_label.text() == word_l:
                prons = self._cached_pronunciations(word_l)
                self.analysis.show_word(word_l, prons)
        self._schedule_save()
        self._annotation_timer.start()

    # ---- Word handling ----

    def _on_pronunciation_chosen(self, word, idx):
        """Remember the user's preferred pronunciation, persist it, and refresh trajectory."""
        key = word.lower()
        self._pron_index_cache[key] = idx
        self.active_song.pron_choices[key] = idx
        self._schedule_save()
        self._annotation_timer.start()
        if self._current_block_number >= 0:
            self._update_trajectory(self.editor.line_text(self._current_block_number))

    def _context_aware_pronunciations(self, word, next_ipa=None):
        """Like _cached_pronunciations but applies next-word context rules.

        Feature 4: 'the' → /ði/ before a vowel, /ðə/ before a consonant.
        """
        prons = self._cached_pronunciations(word)
        if not next_ipa or word.lower() not in ('the',):
            return prons
        if word.lower() == 'the':
            return ['ði'] if ipa_leading_vowel(next_ipa) is not None else ['ðə']
        return prons

    def _get_next_word_ipa(self, line_text: str, clicked_word: str) -> Optional[str]:
        """Return first pronunciation IPA of the next word, or None if
        there is a punctuation boundary between them.
        """
        matches = list(WORD_RE.finditer(line_text))
        clicked_l = clicked_word.lower()
        for i, m in enumerate(matches):
            if m.group().lower() == clicked_l and i + 1 < len(matches):
                between = line_text[m.end():matches[i + 1].start()]
                if re.search(r'[,;:.!?]', between):
                    return None   # punctuation boundary — suppress legato
                next_prons = self._cached_pronunciations(matches[i + 1].group())
                return next_prons[0] if next_prons else None
        return None


    # ---- Inline annotation hints ----

    # Hint type labels for display
    _HINT_TYPE_LABELS = {
        'legato':      'Legato links',
        'vowel_glide': 'Vowel glides (anti-glottal)',
        'crash':       'Consonant crashes',
        'r_toxicity':  'R toxicity',
        'dark_l':      'Dark L trap',
        'glottal':     'Phrase-initial glottal',
        'plosive':     'Plosive exits',
        'nasal':       'Nasal exits',
        'approx':      'Approximant exits',
        'fricative':   'Fricative exits',
    }

    def _build_hints_menu(self) -> QMenu:
        menu = QMenu(self)
        # Master on/off toggle at the top
        self._act_hints_enabled = QAction('Hints enabled', menu)
        self._act_hints_enabled.setCheckable(True)
        self._act_hints_enabled.setChecked(True)
        self._act_hints_enabled.triggered.connect(self._on_hints_toggled)
        menu.addAction(self._act_hints_enabled)
        menu.addSeparator()
        # Convenience bulk actions
        a_all = QAction('Enable all types', menu)
        a_all.triggered.connect(lambda: self._set_all_hint_types(True))
        menu.addAction(a_all)
        a_none = QAction('Disable all types', menu)
        a_none.triggered.connect(lambda: self._set_all_hint_types(False))
        menu.addAction(a_none)
        menu.addSeparator()
        # Per-type checkable actions
        for tip_type, label in self._HINT_TYPE_LABELS.items():
            act = QAction(label, menu)
            act.setCheckable(True)
            act.setChecked(tip_type in self._enabled_hint_types)
            act.triggered.connect(
                lambda checked, t=tip_type: self._on_hint_type_toggled(t, checked))
            menu.addAction(act)
        return menu

    def _update_hints_btn_label(self):
        n = len(self._enabled_hint_types)
        total = len(self._HINT_TYPE_LABELS)
        if not self._annotations_enabled:
            self.hints_btn.setText('HINTS (off)')
        elif n == total:
            self.hints_btn.setText('HINTS')
        else:
            self.hints_btn.setText(f'HINTS ({n}/{total})')

    def _set_all_hint_types(self, enabled: bool):
        if enabled:
            self._enabled_hint_types = set(self._HINT_TYPE_LABELS.keys())
        else:
            self._enabled_hint_types = set()
        # Sync checkmarks in menu
        for act in self._hints_menu.actions():
            if act.isCheckable():
                act.setChecked(enabled)
        self._update_hints_btn_label()
        self._compute_annotations()

    def _on_hint_type_toggled(self, tip_type: str, checked: bool):
        if checked:
            self._enabled_hint_types.add(tip_type)
        else:
            self._enabled_hint_types.discard(tip_type)
        self._update_hints_btn_label()
        self._compute_annotations()

    def _on_hints_toggled(self, checked: bool):
        self._annotations_enabled = checked
        # Keep the menu action checkmark in sync
        if hasattr(self, '_act_hints_enabled'):
            self._act_hints_enabled.setChecked(checked)
        self._update_hints_btn_label()
        if checked:
            self._compute_annotations()
        else:
            self.editor.clear_annotations()

    def _on_annotation_dismissed(self, word_lower: str):
        self.active_song.dismissed_tips.add(word_lower)
        self._schedule_save()
        self._compute_annotations()

    def _on_reset_dismissed_hints(self):
        self.active_song.dismissed_tips.clear()
        self._schedule_save()
        self._compute_annotations()

    def _compute_annotations(self):
        """Scan all lyrics and compute inline diction annotations."""
        if not self._annotations_enabled:
            self.editor.clear_annotations()
            return
        doc = self.editor.document()
        dismissed = self.active_song.dismissed_tips
        annotations = []

        for block_num in range(doc.blockCount()):
            block = doc.findBlockByNumber(block_num)
            line_text = block.text()
            matches = list(WORD_RE.finditer(line_text))

            for i, m in enumerate(matches):
                word = m.group()
                word_l = word.lower()
                if word_l in dismissed:
                    continue

                # ── glottal onset check (this word opens a phrase) ────────
                # True if word is first on the line, or preceded by punctuation
                phrase_opener = (i == 0)
                if not phrase_opener and i > 0:
                    before = line_text[matches[i-1].end():m.start()]
                    phrase_opener = bool(re.search(r'[,;:.!?]', before))
                if phrase_opener and 'glottal' in self._enabled_hint_types:
                    # Only flag if the word starts with a vowel
                    prons_check = self._cached_pronunciations(word)
                    preferred_c = self._pron_index_cache.get(word_l, 0)
                    pron_check = prons_check[min(preferred_c, len(prons_check)-1)] if prons_check else ''
                    if pron_check and ipa_leading_vowel(pron_check) is not None and word_l not in dismissed:
                        annotations.append(WordAnnotation(
                            word=word, word_lower=word_l,
                            block=block_num, start=m.start(), end=m.end(),
                            abs_start=block.position() + m.start(),
                            abs_end=block.position() + m.end(),
                            tip_type='glottal',
                            tip_text=('Phrase-initial glottal \u2014 this phrase opens on a vowel. '
                                      'Use a clean balanced onset: let the breath flow a split-second '
                                      'before the tone. Avoid a glottal strike (colpo di glottide).'),
                            color=ANN_COLOR['glottal'],
                            bg_color=ANN_BG['glottal'],
                        ))

                # ── next-word context ─────────────────────────────────────
                next_ipa = None
                has_punct_boundary = False
                if i + 1 < len(matches):
                    between = line_text[m.end():matches[i + 1].start()]
                    has_punct_boundary = bool(re.search(r'[,;:.!?]', between))
                    np = self._cached_pronunciations(matches[i + 1].group())
                    next_ipa = np[0] if np else None

                prons = self._context_aware_pronunciations(
                    word, None if has_punct_boundary else next_ipa)
                if not prons:
                    continue
                preferred = self._pron_index_cache.get(word_l, 0)
                pron = prons[min(preferred, len(prons) - 1)]
                trailing  = ipa_trailing_consonants(pron)
                end_vowel = ipa_ends_with_vowel(pron)

                # ── classify ──────────────────────────────────────────────────
                next_leading_v = (ipa_leading_vowel(next_ipa)
                                  if next_ipa and not has_punct_boundary else None)
                next_leading_c = (ipa_leading_consonant(next_ipa)
                                  if next_ipa and not has_punct_boundary else None)
                plosives   = [c for c in trailing if c in IPA_PLOSIVES]
                nasals     = [c for c in trailing if c in IPA_NASALS]
                approx     = [c for c in trailing if c in IPA_APPROXIMANTS]
                rhotics    = [c for c in trailing if c in IPA_RHOTIC]
                fricatives = [c for c in trailing if c in IPA_FRICATIVES]

                # R-colored vowels count as rhotic even without trailing /r/
                has_rhotic_vowel = any(
                    s in ('ɚ', 'ɝ') for s, _, _ in find_syllable_vowels(pron))

                tip_type = tip = None

                # 1. Legato (consonant end → next vowel start, no punct)
                if trailing and next_leading_v is not None:
                    cd = ' '.join(f'/{c}/' for c in trailing)
                    tip = (f'Legato — carry {cd} into the opening /{next_leading_v}/ '
                           f'of the next word. Keep the breath connected.')
                    tip_type = 'legato'

                # 2. Vowel-to-vowel glide (word ends on vowel, next starts vowel)
                elif end_vowel is not None and next_leading_v is not None:
                    glide = '/j/' if end_vowel in _GLIDE_J else '/w/'
                    tip = (f'Vowel-to-vowel — insert a soft {glide} glide to avoid '
                           f'a glottal stop before /{next_leading_v}/. Keep airflow open.')
                    tip_type = 'vowel_glide'

                # 3. Consonant crash
                elif trailing and next_leading_c is not None:
                    crash = consonant_crash_tip(trailing, next_leading_c)
                    if crash:
                        tip, tip_type = crash, 'crash'

                # 4. R toxicity (trailing /r/ consonant or rhotic vowel)
                if tip_type is None and (rhotics or has_rhotic_vowel):
                    tip = ('American R — de-rhotacize: release the tongue curl/bunch '
                           'before the note sustains. Sustain on the base vowel '
                           '(ə or ɜ) instead of the r-colored form.')
                    tip_type = 'r_toxicity'

                # 5. Dark L — trailing /l/ not already captured as legato/crash
                if tip_type is None and trailing and trailing[-1] == 'l':
                    tip = ('Dark L exit \u2014 keep the tongue tip on the alveolar '
                           'ridge. Do not pull the tongue root back; that '
                           'swallows the resonance and darkens the sound.')
                    tip_type = 'dark_l'

                # 6. Consonant exit tips (no boundary interaction found above)
                if tip_type is None:
                    if plosives:
                        s = ' '.join(f'/{c}/' for c in plosives)
                        tip = f'Plosive exit {s} — snap off cleanly, no shadow vowel.'
                        tip_type = 'plosive'
                    elif nasals:
                        s = ' '.join(f'/{c}/' for c in nasals)
                        tip = f'Nasal exit {s} — carries pitch; sustain through it.'
                        tip_type = 'nasal'
                    elif approx and not rhotics:
                        s = ' '.join(f'/{c}/' for c in approx)
                        tip = f'Approximant exit {s} — gentle release, no hard cutoff.'
                        tip_type = 'approx'
                    elif fricatives:
                        s = ' '.join(f'/{c}/' for c in fricatives)
                        tip = f'Fricative exit {s} — control the airstream.'
                        tip_type = 'fricative'

                if tip_type is None:
                    continue
                if tip_type not in self._enabled_hint_types:
                    continue

                annotations.append(WordAnnotation(
                    word=word, word_lower=word_l,
                    block=block_num, start=m.start(), end=m.end(),
                    abs_start=block.position() + m.start(),
                    abs_end=block.position() + m.end(),
                    tip_type=tip_type, tip_text=tip,
                    color=ANN_COLOR[tip_type],
                    bg_color=ANN_BG[tip_type],
                ))

        self._word_annotations = annotations
        self.editor.set_annotations(annotations)

    def _on_word_clicked(self, word, block_number):
        self._current_block_number = block_number
        line = self.editor.line_text(block_number)
        next_ipa = self._get_next_word_ipa(line, word)
        prons = self._context_aware_pronunciations(word, next_ipa)
        preferred = self._pron_index_cache.get(word.lower(), 0)
        self.analysis.show_word(word, prons, initial_index=preferred, next_ipa=next_ipa)
        self._update_trajectory(line)

    def _cached_pronunciations(self, word):
        cache_key = word.lower()
        if cache_key not in self._pron_cache:
            self._pron_cache[cache_key] = get_pronunciations(
                word, self.active_song.custom_ipa)
        return self._pron_cache[cache_key]

    def _update_trajectory(self, line_text):
        items = []
        word_idx = 0
        clicked_word = self.analysis.word_label.text()
        clicked_word_idx = -1
        matches = list(WORD_RE.finditer(line_text))
        for i, m in enumerate(matches):
            w = m.group()
            # Next word's IPA for context-aware function-word resolution
            next_ipa = None
            if i + 1 < len(matches):
                np = self._cached_pronunciations(matches[i + 1].group())
                next_ipa = np[0] if np else None
            prons = self._context_aware_pronunciations(w, next_ipa)
            if not prons:
                word_idx += 1
                continue
            preferred_idx = self._pron_index_cache.get(w.lower(), 0)
            pron = prons[min(preferred_idx, len(prons) - 1)]
            syls = find_syllable_vowels(pron)
            for sym, _, _ in syls:
                items.append((sym, word_idx))
            if w.lower() == clicked_word.lower():
                clicked_word_idx = word_idx
            word_idx += 1
        self._current_line_items = items
        self._current_clicked_word_idx = clicked_word_idx
        self.trajectory.set_phrase(items)
        self._update_chiaroscuro(items)
        self._update_breath_and_sibilance(line_text)

    def _update_breath_and_sibilance(self, line_text: str):
        """Scan the raw line IPA for unvoiced density and sibilant clusters."""
        matches = list(WORD_RE.finditer(line_text))
        all_phones = []
        for m in matches:
            prons = self._cached_pronunciations(m.group())
            if prons:
                preferred = self._pron_index_cache.get(m.group().lower(), 0)
                pron = prons[min(preferred, len(prons) - 1)]
                # Collect all consonant tokens from this pron
                for ch in pron:
                    if ch in IPA_ALL_CONS:
                        all_phones.append(ch)
                # Also check digraphs
                for digraph in ('tʃ', 'dʒ'):
                    if digraph in pron:
                        all_phones.append(digraph)

        # Breath leak
        if all_phones:
            unvoiced = sum(1 for p in all_phones if p in IPA_UNVOICED)
            ratio = unvoiced / len(all_phones)
            if ratio >= 0.55:
                self.breath_label.setText(
                    f'\u2697 High unvoiced consonant density ({ratio:.0%}) \u2014 '
                    f'these open the glottis and dump air. '
                    f'Pace your support actively; engage the intercostals '
                    f'to maintain sub-glottal pressure throughout.')
                self.breath_label.setVisible(True)
            else:
                self.breath_label.setVisible(False)
        else:
            self.breath_label.setVisible(False)

        # Sibilance
        sibilants = [p for p in all_phones if p in IPA_SIBILANT]
        if len(sibilants) >= 3:
            self.sibilance_label.setText(
                f'\u26a0 Sibilant-heavy phrase ({len(sibilants)} sibilants) \u2014 '
                f'on mic: soften and shorten each hiss; de-emphasize the '
                f'tongue-tip contact to reduce piercing highs. '
                f'In the hall: use them to cut through, but keep them forward '
                f'and rhythmically precise.')
            self.sibilance_label.setVisible(True)
        else:
            self.sibilance_label.setVisible(False)

    def _update_chiaroscuro(self, items):
        """Show a brightness-balance warning for the current phrase."""
        if not items:
            self.chiaroscuro_label.setVisible(False)
            return
        avg = sum(brightness(s) for s, _ in items) / len(items)
        if avg > 0.63:
            msg = (f'Very bright phrase (∅ {avg:.0%}) — risk of shrill resonance. '
                   f'Counter-balance: round lips on eligible vowels, '
                   f'or modify toward darker variants at high pitch.')
            self.chiaroscuro_label.setText(msg)
            self.chiaroscuro_label.setVisible(True)
        elif avg < 0.37:
            msg = (f'Very dark phrase (∅ {avg:.0%}) — risk of muffled tone. '
                   f'Keep the sound forward; resist swallowing. '
                   f'Brighten on eligible vowels to restore chiaroscuro balance.')
            self.chiaroscuro_label.setText(msg)
            self.chiaroscuro_label.setVisible(True)
        else:
            self.chiaroscuro_label.setVisible(False)

    def _on_vowel_selected_in_analysis(self, syllable_idx):
        if not self._current_line_items:
            return
        if self._current_clicked_word_idx < 0:
            return
        target = -1
        running = 0
        for i, (_, wi) in enumerate(self._current_line_items):
            if wi == self._current_clicked_word_idx:
                if running == syllable_idx:
                    target = i
                    break
                running += 1
        self.trajectory.set_highlight(target)

    def _play_vowel(self, sym):
        candidates = [sym]
        if sym in DIPHTHONGS:
            candidates.append(DIPHTHONGS[sym].primary)
        # R-colored vowels fall back to their base vowel if no dedicated audio
        if sym == 'ɝ':
            candidates.append('ɜ')
        elif sym == 'ɚ':
            candidates.append('ə')
        for c in candidates:
            audio = self._resource_path(path.join('Audio', f'{c}.mp3'))
            if path.exists(audio):
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(audio)))
                self.player.play()
                return

    @staticmethod
    def _resource_path(relative):
        base = getattr(sys, '_MEIPASS',
                       path.dirname(path.abspath(__file__)))
        return path.join(base, relative)

    # ---- Bulk import / prompt generation ----

    def _on_bulk_import(self):
        dlg = BulkImportDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.parsed()
        if data is None:
            QMessageBox.warning(
                self, 'Invalid JSON',
                "Couldn't parse that as a JSON object mapping words to IPA.")
            return
        if not data:
            return
        self.active_song.custom_ipa.update(data)
        self._pron_cache.clear()
        if self._current_block_number >= 0:
            line = self.editor.line_text(self._current_block_number)
            self._update_trajectory(line)
        QMessageBox.information(
            self, 'Imported',
            f'Imported {len(data)} custom IPA entries.')
        self._schedule_save()
        self._annotation_timer.start()

    def _on_generate_prompt(self):
        lyrics = self.editor.toPlainText()
        seen = set()
        unknown = []
        for m in WORD_RE.finditer(lyrics):
            w = m.group().lower()
            if w in seen:
                continue
            seen.add(w)
            if w in self.active_song.custom_ipa:
                continue
            if w in FUNCTION_WORDS:
                continue
            raw = ipa.convert(w, retrieve_all=True) or []
            cleaned = [p for p in raw if p and '*' not in p]
            if not cleaned:
                unknown.append(w)

        prompt = (
            "I'm singing the following song. Please provide an IPA "
            "transcription for each of the unrecognized words listed "
            "below — proper nouns, foreign names, numbers, and so on. "
            "Use standard IPA. Return JSON only: a single object mapping "
            "the word (lowercase) to the IPA string. No prose, no code "
            "fences.\n\n"
            f"Song: {self.active_song.name}\n\n"
            "Words to transcribe:\n"
            + "\n".join(f"- {w}" for w in unknown)
            + "\n\nLyrics for context:\n"
            + lyrics
        )
        clipboard = QApplication.clipboard()
        clipboard.setText(prompt)
        QMessageBox.information(
            self, 'Prompt Copied',
            f'A prompt for {len(unknown)} unrecognized word(s) has been '
            f'copied to your clipboard. Paste it to an AI, then use '
            f'Song → Bulk Import IPAs… with the returned JSON.')

    def _on_open_save_folder(self):
        path_ = self.store.dir
        os.makedirs(path_, exist_ok=True)
        if sys.platform == 'darwin':
            os.system(f'open "{path_}"')
        elif sys.platform == 'win32':
            os.system(f'explorer "{path_}"')
        else:
            os.system(f'xdg-open "{path_}"')

    def _restore_state(self):
        geo = self.settings.value('geometry')
        if geo:
            self.restoreGeometry(geo)
        state = self.settings.value('windowState')
        if state:
            self.restoreState(state)

    def closeEvent(self, event):
        self.active_song.lyrics = self.editor.toPlainText()
        self._persist_songs()
        self.settings.setValue('geometry', self.saveGeometry())
        self.settings.setValue('windowState', self.saveState())
        super().closeEvent(event)


def main():
    # ── HiDPI flags must come before QApplication() ───────────────────────────
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor('#14181f'))
    pal.setColor(QPalette.WindowText, QColor('#d8dfe8'))
    pal.setColor(QPalette.Base, QColor('#1c2230'))
    pal.setColor(QPalette.Text, QColor('#d8dfe8'))
    pal.setColor(QPalette.Button, QColor('#1c2230'))
    pal.setColor(QPalette.ButtonText, QColor('#d8dfe8'))
    pal.setColor(QPalette.Highlight, QColor('#7898d0'))
    pal.setColor(QPalette.HighlightedText, QColor('#14181f'))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()