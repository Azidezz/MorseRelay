# main.py
"""
MorseRelay — Entry Point
=========================
A serene, dark-mode Morse code communication app for Windows.
"""

import sys
import threading
import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray

from settings import Settings, THEMES
from morse import MorseTranslator, TapModeController, MorseMessage
from audio import AudioEngine
from network import NetworkManager
from keyboard_hook import KeyboardHookManager
from dashboard import Dashboard


def create_tray_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([12, 26, 22, 36], fill="white")
    draw.rounded_rectangle([28, 27, 54, 35], radius=3, fill="white")
    return img


class MorseRelayApp:
    def __init__(self):
        self.settings = Settings.load()
        self.settings.recompute_timing_from_wpm()
        self.theme = THEMES[self.settings.theme_shade]

        self.audio = AudioEngine(
            frequency=self.settings.frequency,
            volume=self.settings.volume,
            wpm=self.settings.wpm,
        )
        self.network = NetworkManager(
            callsign=self.settings.callsign,
            port=self.settings.port,
        )
        
        self.kb = KeyboardHookManager()
        self.kb.set_tap_key(self.settings.send_key)  # Uses the single unified tap key
        self.kb.start()

        self.tap = TapModeController(
            dot_threshold=self.settings.dot_threshold,
            letter_gap=self.settings.letter_gap,
            word_gap=self.settings.word_gap,
        )

        self.dashboard: Dashboard | None = None
        self.tray_icon: pystray.Icon | None = None
        self._running = False

    def run(self):
        self._running = True
        self.dashboard = Dashboard(self)
        self.dashboard.mainloop()

    def show_tray_notification(self, title: str, message: str):
        if self.tray_icon:
            self.tray_icon.notify(message, title)

    def setup_tray(self):
        if self.tray_icon: return
        image = create_tray_icon_image()
        menu = pystray.Menu(
            pystray.MenuItem("Show Dashboard", self._tray_show, default=True),
            pystray.MenuItem("Shrink to Mini", self._tray_mini),
            pystray.MenuItem("Test Tone", self._tray_test),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._tray_exit),
        )
        self.tray_icon = pystray.Icon("MorseRelay", image, "MorseRelay", menu)
        tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        tray_thread.start()

    def _tray_show(self, icon=None, item=None):
        if self.dashboard: self.dashboard.show_from_tray()

    def _tray_mini(self, icon=None, item=None):
        if self.dashboard: self.dashboard._shrink_to_mini()

    def _tray_test(self, icon=None, item=None):
        self.audio.play_test_tone(200)

    def _tray_exit(self, icon=None, item=None):
        self.quit_app()

    def quit_app(self):
        self._running = False
        self.audio.stop()
        self.network.stop_listening()
        self.kb.stop()
        self.settings.save()
        if self.tray_icon: self.tray_icon.stop()
        if self.dashboard: self.dashboard.destroy()
        sys.exit(0)


def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    app = MorseRelayApp()
    app.setup_tray()
    try:
        app.run()
    except KeyboardInterrupt:
        app.quit_app()

if __name__ == "__main__":
    main()