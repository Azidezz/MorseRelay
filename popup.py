# popup.py
"""Receiver popup — a graceful, rounded, non-focus-stealing window."""

import sys
import time
import customtkinter as ctk
from typing import Callable, Optional
from datetime import datetime

from settings import THEMES
from morse import MorseTranslator

class MorsePopup(ctk.CTkToplevel):
    TRANSPARENT_COLOR = "#FF00FF"

    def __init__(self, settings, theme: dict, on_repeat: Callable = None, on_reply: Callable = None, on_close: Callable = None):
        super().__init__()
        self.settings = settings
        self.theme = theme
        self._on_repeat = on_repeat
        self._on_reply = on_reply
        self._on_close = on_close
        self._show_translation = settings.show_translation
        self._alpha = 0.0
        self._auto_hide_job = None
        self._char_index = 0
        self._morse_chars: list[str] = []
        self._build_window()
        self._build_content()

    def _build_window(self):
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        if sys.platform == "win32":
            self.configure(fg_color=self.TRANSPARENT_COLOR)
            self.attributes("-transparentcolor", self.TRANSPARENT_COLOR)
        else:
            self.configure(fg_color=self.theme["bg"])
        self._position_window()
        self.attributes("-alpha", 0.0)
        self.after(10, self._fade_in)

    def _position_window(self):
        self.update_idletasks()
        w, h = 420, 150
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        margin = 24
        corner = self.settings.popup_corner
        if corner == "top-left": x, y = margin, margin
        elif corner == "top-right": x, y = screen_w - w - margin, margin
        elif corner == "bottom-left": x, y = margin, screen_h - h - margin - 40
        else: x, y = screen_w - w - margin, screen_h - h - margin - 40
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _final_position(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        margin = 24
        corner = self.settings.popup_corner
        if corner == "top-left": x, y = margin, margin
        elif corner == "top-right": x, y = screen_w - w - margin, margin
        elif corner == "bottom-left": x, y = margin, screen_h - h - margin - 40
        else: x, y = screen_w - w - margin, screen_h - h - margin - 40
        if not self.settings.popup_locked: return
        self.geometry(f"+{x}+{y}")

    def _build_content(self):
        self.outer = ctk.CTkFrame(self, corner_radius=16, fg_color=self.theme["card"], border_width=1, border_color=self.theme["border"])
        self.outer.pack(fill="both", expand=True, padx=2, pady=2)
        if not self.settings.popup_locked: self._enable_drag(self.outer)

        header = ctk.CTkFrame(self.outer, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))

        self.eye_label = ctk.CTkLabel(header, text="👁", font=ctk.CTkFont(size=16), cursor="hand2", text_color=self.theme["secondary"])
        self.eye_label.pack(side="left", padx=(0, 6))
        self.eye_label.bind("<Button-1>", lambda e: self._toggle_translation())

        self.sender_label = ctk.CTkLabel(header, text="✉ msg from —", font=ctk.CTkFont(size=12, weight="bold"), text_color=self.theme["secondary"])
        self.sender_label.pack(side="left")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        self.repeat_label = ctk.CTkLabel(btn_frame, text="⟲", font=ctk.CTkFont(size=16), cursor="hand2", text_color=self.theme["secondary"])
        self.repeat_label.pack(side="left", padx=4)
        self.repeat_label.bind("<Button-1>", lambda e: self._repeat())

        self.reply_label = ctk.CTkLabel(btn_frame, text="↩", font=ctk.CTkFont(size=16), cursor="hand2", text_color=self.theme["secondary"])
        self.reply_label.pack(side="left", padx=4)
        self.reply_label.bind("<Button-1>", lambda e: self._reply())

        self.close_label = ctk.CTkLabel(btn_frame, text="✕", font=ctk.CTkFont(size=16), cursor="hand2", text_color=self.theme["secondary"])
        self.close_label.pack(side="left", padx=4)
        self.close_label.bind("<Button-1>", lambda e: self._close())

        ctk.CTkFrame(self.outer, fg_color=self.theme["border"], height=1).pack(fill="x", padx=14, pady=2)

        self.morse_label = ctk.CTkLabel(self.outer, text="", font=ctk.CTkFont(family="Consolas", size=22, weight="bold"), text_color=self.theme["dot"], anchor="center")
        self.morse_label.pack(fill="x", padx=16, pady=(8, 2))

        self.translation_label = ctk.CTkLabel(self.outer, text="", font=ctk.CTkFont(family="Consolas", size=13), text_color=self.theme["faded"], anchor="center")
        if self._show_translation: self.translation_label.pack(fill="x", padx=16, pady=(0, 4))

        footer = ctk.CTkFrame(self.outer, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(2, 10))

        self.timestamp_label = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=10), text_color=self.theme["faded"])
        self.timestamp_label.pack(side="right")

    def show_message(self, callsign: str, morse: str, text: str, timestamp: float = None):
        if timestamp is None: timestamp = time.time()
        self.sender_label.configure(text=f"✉ msg from {callsign}", text_color=self.theme["text"])
        self.morse_label.configure(text=morse)
        self.translation_label.configure(text=text)
        ts_str = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
        self.timestamp_label.configure(text=ts_str)
        self._morse_chars = list(morse)
        self._char_index = 0
        self.after(50, self._final_position)
        if self._auto_hide_job: self.after_cancel(self._auto_hide_job)
        if self.settings.popup_duration > 0:
            self._auto_hide_job = self.after(self.settings.popup_duration * 1000, self._close)

    def highlight_char(self, index: int):
        if index < 0 or index >= len(self._morse_chars): return
        self._char_index = index
        before = "".join(self._morse_chars[:index])
        current = self._morse_chars[index]
        after = "".join(self._morse_chars[index + 1:])
        display = f"{before}{current}{after}"
        self.morse_label.configure(text=display)

    def _toggle_translation(self):
        self._show_translation = not self._show_translation
        if self._show_translation:
            self.translation_label.pack(fill="x", padx=16, pady=(0, 4))
            self.eye_label.configure(text_color=self.theme["text"])
        else:
            self.translation_label.pack_forget()
            self.eye_label.configure(text_color=self.theme["secondary"])
        self.after(50, self._final_position)

    def _repeat(self):
        if self._on_repeat: self._on_repeat()

    def _reply(self):
        if self._on_reply: self._on_reply()

    def _close(self):
        self._fade_out()

    def _fade_in(self):
        self._alpha += 0.08
        if self._alpha >= 1.0:
            self._alpha = 1.0
            self.attributes("-alpha", 1.0)
            return
        self.attributes("-alpha", self._alpha)
        self.after(16, self._fade_in)

    def _fade_out(self):
        self._alpha -= 0.10
        if self._alpha <= 0.0:
            self.attributes("-alpha", 0.0)
            if self._on_close: self._on_close()
            self.destroy()
            return
        self.attributes("-alpha", self._alpha)
        self.after(16, self._fade_out)

    def _enable_drag(self, widget):
        def start(e):
            self._drag_x = e.x_root - self.winfo_x()
            self._drag_y = e.y_root - self.winfo_y()
        def drag(e):
            x = e.x_root - self._drag_x
            y = e.y_root - self._drag_y
            self.geometry(f"+{x}+{y}")
        widget.bind("<ButtonPress-1>", start)
        widget.bind("<B1-Motion>", drag)
        for child in widget.winfo_children():
            child.bind("<ButtonPress-1>", start)
            child.bind("<B1-Motion>", drag)