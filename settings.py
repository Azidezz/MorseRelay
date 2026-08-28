# settings.py
"""Settings model with JSON persistence."""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".morse_relay")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")

@dataclass
class Settings:
    callsign: str = "NODE01"
    frequency: int = 700
    volume: float = 0.45
    wpm: int = 20
    dot_threshold: int = 200
    letter_gap: int = 180
    word_gap: int = 420
    auto_timing: bool = True
    send_key: str = "delete"  # Used as the universal Tap Key
    target_ip: str = ""
    port: int = 7777
    auto_listen: bool = True
    popup_corner: str = "bottom-right"
    popup_locked: bool = True
    show_popup: bool = True
    play_audio: bool = True
    show_translation: bool = False
    popup_duration: int = 6
    theme_shade: str = "pure-black"
    minimize_to_tray_on_close: bool = True
    history: list = field(default_factory=list)

    def save(self):
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Settings":
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**valid)
            except Exception:
                pass
        return cls()

    def recompute_timing_from_wpm(self):
        if not self.auto_timing: return
        dot_ms = 1200.0 / self.wpm
        self.dot_threshold = int(dot_ms * 2)
        self.letter_gap = int(dot_ms * 3)
        self.word_gap = int(dot_ms * 7)

THEMES = {
    "pure-black":  {"bg": "#0A0A0A", "card": "#161616", "card_hover": "#1E1E1E",
                    "border": "#2A2A2A", "text": "#EAEAEA", "secondary": "#7A7A7A",
                    "faded": "#4A4A4A", "accent": "#FFFFFF", "dot": "#EAEAEA"},
    "dark-gray":   {"bg": "#141414", "card": "#1E1E1E", "card_hover": "#262626",
                    "border": "#333333", "text": "#E0E0E0", "secondary": "#808080",
                    "faded": "#505050", "accent": "#FFFFFF", "dot": "#E0E0E0"},
    "midnight":    {"bg": "#0C0E14", "card": "#161922", "card_hover": "#1E2230",
                    "border": "#2A2E3C", "text": "#DDE2EE", "secondary": "#6E7488",
                    "faded": "#3E4458", "accent": "#E8ECF4", "dot": "#DDE2EE"},
}