# keyboard_hook.py
"""Global keyboard hook using the `keyboard` library."""

import keyboard
from typing import Callable, Optional

class KeyboardHookManager:
    def __init__(self):
        self.tap_key: Optional[str] = None
        self.backspace_key: Optional[str] = None
        self.on_tap_down: Optional[Callable[[], None]] = None
        self.on_tap_up: Optional[Callable[[], None]] = None
        self.on_backspace_down: Optional[Callable[[], None]] = None

        self._hook_handle = None
        self._capturing: str = ""  # "tap" | "backspace" | ""
        self._capture_callback: Optional[Callable[[str], None]] = None
        self._started = False
        self._tap_key_is_down = False
        self._backspace_key_is_down = False

    def start(self):
        if self._started: return
        self._started = True
        self._hook_handle = keyboard.hook(self._on_event, suppress=False)

    def stop(self):
        if self._hook_handle:
            keyboard.unhook(self._hook_handle)
            self._hook_handle = None
        self._started = False

    def set_tap_key(self, key_name: str): self.tap_key = key_name
    def set_backspace_key(self, key_name: str): self.backspace_key = key_name

    def capture_next_key(self, target: str, callback: Callable[[str], None]):
        self._capturing = target
        self._capture_callback = callback

    def _on_event(self, event):
        if self._capturing and event.event_type == keyboard.KEY_DOWN:
            key_name = event.name
            if key_name in ("ctrl", "shift", "alt", "left ctrl", "right ctrl", "left shift", "right shift", "left alt", "right alt", "left windows", "right windows"):
                return
            cb = self._capture_callback
            self._capturing = ""
            self._capture_callback = None
            if cb: cb(key_name)
            return

        if event.name == self.tap_key:
            if event.event_type == keyboard.KEY_DOWN:
                if not self._tap_key_is_down:
                    self._tap_key_is_down = True
                    if self.on_tap_down: self.on_tap_down()
            elif event.event_type == keyboard.KEY_UP:
                self._tap_key_is_down = False
                if self.on_tap_up: self.on_tap_up()
                
        elif event.name == self.backspace_key and self.on_backspace_down:
            if event.event_type == keyboard.KEY_DOWN:
                if not self._backspace_key_is_down:
                    self._backspace_key_is_down = True
                    self.on_backspace_down()
            elif event.event_type == keyboard.KEY_UP:
                self._backspace_key_is_down = False

    @staticmethod
    def get_key_display_name(key_name: str) -> str:
        display_map = {
            "space": "Space", "delete": "Delete", "backspace": "Backspace",
            "enter": "Enter", "tab": "Tab", "esc": "Escape", "decimal": "Numpad .",
            "num lock": "Num Lock", "caps lock": "Caps Lock",
        }
        if key_name in display_map: return display_map[key_name]
        if key_name.startswith("numpad "): return "Numpad " + key_name[7:].upper()
        if len(key_name) == 1: return key_name.upper()
        return key_name.title()