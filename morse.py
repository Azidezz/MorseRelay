# morse.py
"""Morse code translator, data models, and tap-mode state machine."""

import re
import time
import threading
from dataclasses import dataclass
from typing import Optional, Callable

TEXT_TO_MORSE: dict[str, str] = {
    "A": ".-",    "B": "-...",  "C": "-.-.",  "D": "-..",   "E": ".",
    "F": "..-.",  "G": "--.",   "H": "....",  "I": "..",    "J": ".---",
    "K": "-.-",   "L": ".-..",  "M": "--",    "N": "-.",    "O": "---",
    "P": ".--.",  "Q": "--.-",  "R": ".-.",   "S": "...",   "T": "-",
    "U": "..-",   "V": "...-",  "W": ".--",   "X": "-..-",  "Y": "-.--",
    "Z": "--..",
    "0": "-----", "1": ".----", "2": "..---", "3": "...--", "4": "....-",
    "5": ".....", "6": "-....", "7": "--...", "8": "---..", "9": "----.",
    ".": ".-.-.-", ",": "--..--", "?": "..--..", "/": "-..-.",
    "-": "-....-", "=": "-...-",  ":": "---...", ";": "-.-.-.",
    "!": "-.-.--", "(": "-.--.",  ")": "-.--.-", "&": ".-...",
    "+": ".-.-.",  '"': ".-..-.", "@": ".--.-.", "'": ".----.",
}
MORSE_TO_TEXT: dict[str, str] = {v: k for k, v in TEXT_TO_MORSE.items()}

class MorseTranslator:
    @staticmethod
    def encode(text: str) -> str:
        parts: list[str] = []
        for char in text.upper():
            if char == " ":
                if parts and parts[-1] != "/": parts.append("/")
                continue
            m = TEXT_TO_MORSE.get(char)
            if m: parts.append(m)
        return " ".join(parts)

    @staticmethod
    def decode(morse: str) -> str:
        words = re.split(r"\s*/\s*", morse.strip())
        result: list[str] = []
        for word in words:
            letters = word.split()
            decoded = [MORSE_TO_TEXT.get(sym, "?") for sym in letters]
            result.append("".join(decoded))
        return " ".join(result)

    @staticmethod
    def decode_letter(morse_letter: str) -> str:
        return MORSE_TO_TEXT.get(morse_letter.strip(), "?")

@dataclass
class MorseMessage:
    callsign: str
    morse: str
    text: str
    timestamp: float
    direction: str = "in"

    def to_dict(self) -> dict:
        return {"callsign": self.callsign, "morse": self.morse, "text": self.text, "timestamp": self.timestamp, "direction": self.direction}

    @classmethod
    def from_dict(cls, d: dict) -> "MorseMessage":
        return cls(callsign=d.get("callsign", "???"), morse=d.get("morse", ""), text=d.get("text", ""), timestamp=d.get("timestamp", time.time()), direction=d.get("direction", "in"))

def validate_callsign(cs: str) -> tuple[bool, str]:
    if not cs: return False, "Callsign cannot be empty."
    if len(cs) < 3: return False, "Callsign must be at least 3 characters."
    if len(cs) > 10: return False, "Callsign must be at most 10 characters."
    if not re.match(r'^[A-Za-z][A-Za-z0-9]{2,9}$', cs): return False, "Must start with a letter; only letters & digits."
    return True, ""

class TapModeController:
    def __init__(self, dot_threshold=200, letter_gap=180, word_gap=420):
        self.dot_threshold = dot_threshold
        self.letter_gap = letter_gap
        self.word_gap = word_gap
        self._morse: str = ""
        self._current_letter: str = ""
        self._key_down_time: Optional[float] = None
        self._letter_timer: Optional[threading.Timer] = None
        self._word_timer: Optional[threading.Timer] = None
        self._active = False
        self.on_morse_updated: Optional[Callable[[str], None]] = None
        self.on_character_decoded: Optional[Callable[[str, str], None]] = None
        self.on_key_state: Optional[Callable[[bool], None]] = None

    @property
    def active(self) -> bool: return self._active

    def start(self):
        self._active = True
        self.reset()

    def stop(self):
        self._active = False
        self._cancel_timers()

    def reset(self):
        self._morse = ""
        self._current_letter = ""
        self._key_down_time = None
        self._cancel_timers()
        if self.on_morse_updated: self.on_morse_updated("")

    def on_key_down(self):
        if not self._active or self._key_down_time is not None: return
        self._key_down_time = time.monotonic()
        self._cancel_timers()
        if self.on_key_state: self.on_key_state(True)

    def on_key_up(self):
        if not self._active or self._key_down_time is None: return
        duration_ms = (time.monotonic() - self._key_down_time) * 1000
        self._key_down_time = None
        if self.on_key_state: self.on_key_state(False)

        if duration_ms < self.dot_threshold: self._current_letter += "."
        else: self._current_letter += "-"
        self._notify()

        self._letter_timer = threading.Timer(self.letter_gap / 1000, self._on_letter_complete)
        self._letter_timer.daemon = True
        self._letter_timer.start()

    def on_backspace(self):
        if not self._active or self._key_down_time is not None: return
        self._cancel_timers()
        
        if self._current_letter:
            self._current_letter = self._current_letter[:-1]
        elif self._morse:
            m = self._morse.rstrip()
            if m.endswith("/"):
                m = m[:-1].rstrip()
            else:
                parts = m.split(" ")
                parts = parts[:-1]
                m = " ".join(parts)
            self._morse = m
        self._notify()

    def _on_letter_complete(self):
        if self._current_letter:
            decoded = MorseTranslator.decode_letter(self._current_letter)
            if self.on_character_decoded: self.on_character_decoded(self._current_letter, decoded)
            if self._morse: self._morse += " "
            self._morse += self._current_letter
            self._current_letter = ""
            self._notify()
            
        remaining = max(0.01, (self.word_gap - self.letter_gap) / 1000)
        self._word_timer = threading.Timer(remaining, self._on_word_complete)
        self._word_timer.daemon = True
        self._word_timer.start()

    def _on_word_complete(self):
        if self._morse and not self._morse.rstrip().endswith("/"):
            self._morse += " / "
            self._notify()

    def _notify(self):
        if self.on_morse_updated: self.on_morse_updated(self.get_display_morse())

    def get_display_morse(self) -> str:
        if self._current_letter:
            if self._morse: return self._morse + " " + self._current_letter
            return self._current_letter
        return self._morse

    def get_final_morse(self) -> str: return self.get_display_morse().strip()
    def get_text(self) -> str: return MorseTranslator.decode(self.get_final_morse())

    def update_timing(self, dot_threshold=None, letter_gap=None, word_gap=None):
        if dot_threshold is not None: self.dot_threshold = dot_threshold
        if letter_gap is not None: self.letter_gap = letter_gap
        if word_gap is not None: self.word_gap = word_gap

    def _cancel_timers(self):
        for t in (self._letter_timer, self._word_timer):
            if t: t.cancel()
        self._letter_timer = None
        self._word_timer = None