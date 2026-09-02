# dashboard.py
"""Main dashboard window + mini window."""

import sys
import time
import threading
import customtkinter as ctk
from tkinter import messagebox
from datetime import datetime
from typing import Optional, Callable

from settings import Settings, THEMES
from morse import MorseTranslator, MorseMessage, TapModeController, validate_callsign, TEXT_TO_MORSE
from audio import AudioEngine
from network import NetworkManager
from keyboard_hook import KeyboardHookManager

class Dashboard(ctk.CTk):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.settings: Settings = app.settings
        self.theme = THEMES[self.settings.theme_shade]
        self.audio: AudioEngine = app.audio
        self.network: NetworkManager = app.network
        self.kb: KeyboardHookManager = app.kb
        self.tap: TapModeController = app.tap
        self.mini_window: Optional["MiniWindow"] = None
        self._tap_mode_active = False
        self._auto_send_after_id = None
        self._auto_send_start_time = 0.0
        self._chart_window = None

        ctk.set_appearance_mode("dark")
        self._apply_theme()
        self._build_ui()
        self._wire_callbacks()
        self._refresh_status()

    def _apply_theme(self):
        t = self.theme
        self.configure(fg_color=t["bg"])
        ctk.set_widget_scaling(1.0)

    def _build_ui(self):
        t = self.theme
        self.title("MorseRelay")
        self.geometry("820x880")
        self.minsize(700, 780)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=t["bg"], corner_radius=0)
        self.scroll.pack(fill="both", expand=True)

        # ── Header ──
        header = ctk.CTkFrame(self.scroll, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(18, 10))

        ctk.CTkLabel(header, text="MorseRelay", font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color=t["text"]).pack(side="left")
        
        # Hidden Morse Chart Button
        chart_btn = ctk.CTkLabel(header, text="❓", font=ctk.CTkFont(size=18), cursor="hand2", text_color=t["secondary"])
        chart_btn.pack(side="left", padx=(12, 0))
        chart_btn.bind("<Button-1>", lambda e: self._show_morse_chart())

        self.status_dot = ctk.CTkLabel(header, text="●", font=ctk.CTkFont(size=14), text_color=t["faded"])
        self.status_dot.pack(side="right", padx=(4, 0))
        self.status_label = ctk.CTkLabel(header, text="Initializing…", font=ctk.CTkFont(family="Segoe UI", size=12), text_color=t["secondary"])
        self.status_label.pack(side="right")

        # ── Row 1: Identity + Connection ──
        row1 = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=4)

        id_card = self._card(row1, "Identity")
        id_card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(id_card, text="Callsign", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(anchor="w", padx=16, pady=(10, 0))
        
        callsign_frame = ctk.CTkFrame(id_card, fg_color="transparent")
        callsign_frame.pack(fill="x", padx=16, pady=4)
        self.callsign_entry = ctk.CTkEntry(callsign_frame, height=34, corner_radius=8, fg_color=t["bg"], border_color=t["border"], text_color=t["text"], border_width=1, font=ctk.CTkFont(size=14, weight="bold"))
        self.callsign_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.callsign_entry.insert(0, self.settings.callsign)
        self.callsign_status = ctk.CTkLabel(callsign_frame, text="✓", font=ctk.CTkFont(size=14), text_color=t["faded"])
        self.callsign_status.pack(side="left")
        self.my_ip_label = ctk.CTkLabel(id_card, text=f"My IP: {self.network.get_local_ip()}", font=ctk.CTkFont(size=11), text_color=t["faded"])
        self.my_ip_label.pack(anchor="w", padx=16, pady=(0, 12))

        conn_card = self._card(row1, "Connection")
        conn_card.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ctk.CTkLabel(conn_card, text="Target IP", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(anchor="w", padx=16, pady=(10, 0))
        self.target_entry = ctk.CTkEntry(conn_card, height=34, corner_radius=8, fg_color=t["bg"], border_color=t["border"], text_color=t["text"], border_width=1, font=ctk.CTkFont(size=13), placeholder_text="192.168.1.x")
        self.target_entry.pack(fill="x", padx=16, pady=4)
        if self.settings.target_ip: self.target_entry.insert(0, self.settings.target_ip)

        port_frame = ctk.CTkFrame(conn_card, fg_color="transparent")
        port_frame.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkLabel(port_frame, text="Port:", font=ctk.CTkFont(size=12), text_color=t["secondary"]).pack(side="left")
        self.port_entry = ctk.CTkEntry(port_frame, width=70, height=28, corner_radius=6, fg_color=t["bg"], border_color=t["border"], text_color=t["text"], border_width=1, font=ctk.CTkFont(size=12), justify="center")
        self.port_entry.pack(side="left", padx=6)
        self.port_entry.insert(0, str(self.settings.port))
        self.listen_btn = ctk.CTkButton(port_frame, text="Listening ●", width=90, height=28, corner_radius=6, font=ctk.CTkFont(size=11), fg_color=t["accent"], text_color=t["bg"], command=self._toggle_listen)
        self.listen_btn.pack(side="right")
        self.peers_label = ctk.CTkLabel(conn_card, text="Discovered: scanning…", font=ctk.CTkFont(size=10), text_color=t["faded"])
        self.peers_label.pack(anchor="w", padx=16, pady=(0, 12))

        # ── Row 2: Audio + Speed ──
        row2 = ctk.CTkFrame(self.scroll, fg_color="transparent")
        row2.pack(fill="x", padx=24, pady=4)

        audio_card = self._card(row2, "Audio")
        audio_card.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._slider_row(audio_card, "Frequency", "freq_slider", 200, 2000, self.settings.frequency, " Hz", self._on_freq_change)
        self._slider_row(audio_card, "Volume", "vol_slider", 0, 100, int(self.settings.volume * 100), "%", self._on_vol_change)
        self.test_btn = ctk.CTkButton(audio_card, text="♪ Test Tone", height=28, corner_radius=8, font=ctk.CTkFont(size=12), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._test_tone)
        self.test_btn.pack(fill="x", padx=16, pady=(4, 12))

        speed_card = self._card(row2, "Speed & Timing")
        speed_card.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self._slider_row(speed_card, "WPM", "wpm_slider", 5, 40, self.settings.wpm, "", self._on_wpm_change)
        self.wpm_info = ctk.CTkLabel(speed_card, text=f"1 dot = {1200/self.settings.wpm:.0f} ms", font=ctk.CTkFont(size=10), text_color=t["faded"])
        self.wpm_info.pack(anchor="w", padx=16)
        self.auto_timing_var = ctk.BooleanVar(value=self.settings.auto_timing)
        ctk.CTkCheckBox(speed_card, text="Auto-timing from WPM", font=ctk.CTkFont(size=11), text_color=t["secondary"], fg_color=t["accent"], variable=self.auto_timing_var, command=self._on_auto_timing_toggle).pack(anchor="w", padx=16, pady=(4, 0))
        self._slider_row(speed_card, "Dot threshold", "dot_slider", 50, 500, self.settings.dot_threshold, " ms", self._on_dot_change)
        self._slider_row(speed_card, "Letter gap", "letter_slider", 100, 800, self.settings.letter_gap, " ms", self._on_letter_gap_change)
        self._slider_row(speed_card, "Word gap", "word_slider", 300, 1500, self.settings.word_gap, " ms", self._on_word_gap_change)

        # ── Row 3: Key Assignment ──
        key_card = self._card(self.scroll, "Key Assignment")
        key_card.pack(fill="x", padx=24, pady=4)
        ctk.CTkLabel(key_card, text="Assign keys to tap out messages and delete mistakes. Each computer uses its own local keys.", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(anchor="w", padx=16, pady=(10, 6))
        
        key_frame = ctk.CTkFrame(key_card, fg_color="transparent")
        key_frame.pack(fill="x", padx=16, pady=(0, 12))

        # Tap Key
        tap_frame = ctk.CTkFrame(key_frame, fg_color="transparent")
        tap_frame.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(tap_frame, text="Your Tap Key", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(anchor="w")
        self.tap_key_btn = ctk.CTkButton(tap_frame, text=KeyboardHookManager.get_key_display_name(self.settings.send_key), height=36, corner_radius=8, fg_color=t["bg"], text_color=t["text"], border_width=1, border_color=t["border"], font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self._capture_key("tap"))
        self.tap_key_btn.pack(fill="x", pady=2)
        self.tap_key_status = ctk.CTkLabel(tap_frame, text="● idle", font=ctk.CTkFont(size=10), text_color=t["faded"])
        self.tap_key_status.pack(anchor="w")

        # Backspace Key
        bsp_frame = ctk.CTkFrame(key_frame, fg_color="transparent")
        bsp_frame.pack(side="left", fill="x", expand=True, padx=(8, 0))
        ctk.CTkLabel(bsp_frame, text="Your Backspace Key", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(anchor="w")
        self.bsp_key_btn = ctk.CTkButton(bsp_frame, text=KeyboardHookManager.get_key_display_name(self.settings.backspace_key), height=36, corner_radius=8, fg_color=t["bg"], text_color=t["text"], border_width=1, border_color=t["border"], font=ctk.CTkFont(size=14, weight="bold"), command=lambda: self._capture_key("backspace"))
        self.bsp_key_btn.pack(fill="x", pady=2)
        self.bsp_key_status = ctk.CTkLabel(bsp_frame, text="● idle", font=ctk.CTkFont(size=10), text_color=t["faded"])
        self.bsp_key_status.pack(anchor="w")

        # ── Row 4: Message Composer ──
        msg_card = self._card(self.scroll, "Message")
        msg_card.pack(fill="x", padx=24, pady=4)
        self.msg_entry = ctk.CTkEntry(msg_card, height=36, corner_radius=8, fg_color=t["bg"], border_color=t["border"], text_color=t["text"], border_width=1, font=ctk.CTkFont(size=14), placeholder_text="Type a message to encode & send…")
        self.msg_entry.pack(fill="x", padx=16, pady=(10, 4))
        self.msg_entry.bind("<KeyRelease>", self._on_msg_type)
        
        self.morse_preview = ctk.CTkLabel(msg_card, text="", font=ctk.CTkFont(family="Consolas", size=14), text_color=t["dot"], anchor="w", justify="left", wraplength=660)
        self.morse_preview.pack(fill="x", padx=16, pady=(0, 4))
        self.tap_display = ctk.CTkLabel(msg_card, text="", font=ctk.CTkFont(family="Consolas", size=14), text_color=t["dot"], anchor="w", justify="left", wraplength=660)
        self.tap_display.pack(fill="x", padx=16, pady=(0, 4))

        # Auto-Send Row
        auto_frame = ctk.CTkFrame(msg_card, fg_color="transparent")
        auto_frame.pack(fill="x", padx=16, pady=(2, 4))
        
        self.auto_send_var = ctk.BooleanVar(value=self.settings.auto_send_enabled)
        ctk.CTkCheckBox(auto_frame, text="Auto-Send", font=ctk.CTkFont(size=12, weight="bold"), text_color=t["text"], fg_color=t["accent"], variable=self.auto_send_var, command=self._on_auto_send_toggle).pack(side="left")
        ctk.CTkLabel(auto_frame, text="Delay (sec):", font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(side="left", padx=(10, 0))
        
        self.auto_delay_slider = ctk.CTkSlider(auto_frame, from_=1, to=10, height=16, width=100, corner_radius=8, fg_color=t["bg"], progress_color=t["accent"], button_color=t["accent"], button_hover_color=t["text"], command=self._on_auto_delay_change)
        self.auto_delay_slider.set(self.settings.auto_send_delay)
        self.auto_delay_slider.pack(side="left", padx=6)
        self.auto_delay_label = ctk.CTkLabel(auto_frame, text=f"{self.settings.auto_send_delay}s", font=ctk.CTkFont(size=11, weight="bold"), text_color=t["text"], width=20)
        self.auto_delay_label.pack(side="left")

        # Visual Progress Bar
        self.auto_send_progress = ctk.CTkProgressBar(msg_card, height=4, fg_color=t["bg"], progress_color=t["accent"])
        self.auto_send_progress.pack(fill="x", padx=16, pady=(0, 8))
        self.auto_send_progress.set(0)

        # Buttons
        btn_frame = ctk.CTkFrame(msg_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(4, 12))
        self.send_btn = ctk.CTkButton(btn_frame, text="Send ▸", width=100, height=32, corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"), fg_color=t["accent"], text_color=t["bg"], command=self._send_message)
        self.send_btn.pack(side="left", padx=(0, 6))
        self.tap_btn = ctk.CTkButton(btn_frame, text="⌨ Tap Mode: OFF", width=140, height=32, corner_radius=8, font=ctk.CTkFont(size=12), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._toggle_tap_mode)
        self.tap_btn.pack(side="left", padx=6)
        self.clear_btn = ctk.CTkButton(btn_frame, text="Clear", width=80, height=32, corner_radius=8, font=ctk.CTkFont(size=12), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._clear_message)
        self.clear_btn.pack(side="left", padx=6)

        # ── Row 5: Popup Settings ──
        popup_card = self._card(self.scroll, "Receiver Popup")
        popup_card.pack(fill="x", padx=24, pady=4)
        corner_frame = ctk.CTkFrame(popup_card, fg_color="transparent")
        corner_frame.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(corner_frame, text="Popup corner:", font=ctk.CTkFont(size=12), text_color=t["secondary"]).pack(side="left")
        self.corner_menu = ctk.CTkOptionMenu(corner_frame, width=140, height=28, values=["top-left", "top-right", "bottom-left", "bottom-right"], fg_color=t["bg"], button_color=t["card_hover"], text_color=t["text"], dropdown_fg_color=t["card"], font=ctk.CTkFont(size=12), command=lambda v: setattr(self.settings, "popup_corner", v))
        self.corner_menu.set(self.settings.popup_corner)
        self.corner_menu.pack(side="left", padx=8)

        chk_frame = ctk.CTkFrame(popup_card, fg_color="transparent")
        chk_frame.pack(fill="x", padx=16, pady=4)
        self.show_popup_var = ctk.BooleanVar(value=self.settings.show_popup)
        self.play_audio_var = ctk.BooleanVar(value=self.settings.play_audio)
        self.show_trans_var = ctk.BooleanVar(value=self.settings.show_translation)
        self.lock_popup_var = ctk.BooleanVar(value=self.settings.popup_locked)

        for label, var, attr in [
            ("Show popup on receive", self.show_popup_var, "show_popup"),
            ("Play audio on receive", self.play_audio_var, "play_audio"),
            ("Show translation by default", self.show_trans_var, "show_translation"),
            ("Lock popup position", self.lock_popup_var, "popup_locked"),
        ]:
            ctk.CTkCheckBox(chk_frame, text=label, font=ctk.CTkFont(size=12), text_color=t["secondary"], fg_color=t["accent"], variable=var, command=lambda a=attr, v=var: self._on_check_change(a, v)).pack(anchor="w", pady=2)
        self._slider_row(popup_card, "Auto-hide after", "duration_slider", 0, 30, self.settings.popup_duration, "s", self._on_duration_change, pad_bottom=12)

        # ── Row 6: History ──
        hist_card = self._card(self.scroll, "Message History")
        hist_card.pack(fill="x", padx=24, pady=4)
        self.history_text = ctk.CTkTextbox(hist_card, height=120, corner_radius=8, fg_color=t["bg"], text_color=t["text"], border_width=1, border_color=t["border"], font=ctk.CTkFont(family="Consolas", size=11))
        self.history_text.pack(fill="x", padx=16, pady=8)
        self._refresh_history()

        # ── Footer ──
        footer = ctk.CTkFrame(self.scroll, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=(4, 24))
        self.mini_btn = ctk.CTkButton(footer, text="▱ Shrink to Mini", height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._shrink_to_mini)
        self.mini_btn.pack(side="left", padx=(0, 8))
        self.tray_btn = ctk.CTkButton(footer, text="▾ Minimize to Tray", height=36, corner_radius=8, font=ctk.CTkFont(size=13), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._minimize_to_tray)
        self.tray_btn.pack(side="left")

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        t = self.theme
        card = ctk.CTkFrame(parent, corner_radius=12, fg_color=t["card"], border_width=1, border_color=t["border"])
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=11, weight="bold"), text_color=t["secondary"]).pack(anchor="w", padx=16, pady=(10, 0))
        return card

    def _slider_row(self, parent, label, attr_name, min_val, max_val, current, suffix, callback, pad_bottom=8):
        t = self.theme
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(2, pad_bottom))
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=11), text_color=t["secondary"]).pack(side="left")
        value_label = ctk.CTkLabel(row, text=f"{current}{suffix}", font=ctk.CTkFont(size=11, weight="bold"), text_color=t["text"])
        value_label.pack(side="right")
        slider = ctk.CTkSlider(frame, from_=min_val, to=max_val, height=16, corner_radius=8, fg_color=t["bg"], progress_color=t["accent"], button_color=t["accent"], button_hover_color=t["text"], command=lambda v: self._slider_callback(callback, v, value_label, suffix))
        slider.set(current)
        slider.pack(fill="x", pady=(2, 0))
        setattr(self, attr_name, slider)
        setattr(self, f"_{attr_name}_label", value_label)

    def _slider_callback(self, callback, value, label, suffix):
        display = str(int(value)) if isinstance(value, float) and value == int(value) else f"{value:.0f}"
        label.configure(text=f"{display}{suffix}")
        callback(value)

    def _wire_callbacks(self):
        self.network.on_message_received = self._on_message_received
        self.network.on_handshake = self._on_handshake
        self.network.on_status = self._on_net_status
        self.network.on_peer_discovered = self._on_peer_discovered

        self.kb.set_tap_key(self.settings.send_key)
        self.kb.set_backspace_key(self.settings.backspace_key)
        self.kb.on_tap_down = self._on_tap_key_down
        self.kb.on_tap_up = self._on_tap_key_up
        self.kb.on_backspace_down = self._on_bsp_key_down

        self.tap.on_morse_updated = lambda m: self.after(0, lambda: self._update_tap_display(m))
        self.tap.on_character_decoded = lambda m, t: None
        self.tap.on_key_state = lambda pressed: self.after(0, lambda: self._update_key_status(pressed))

        self.callsign_entry.bind("<FocusOut>", lambda e: self._save_callsign())
        self.callsign_entry.bind("<Return>", lambda e: self._save_callsign())
        self.target_entry.bind("<FocusOut>", lambda e: self._save_target_ip())
        self.port_entry.bind("<FocusOut>", lambda e: self._save_port())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _save_callsign(self):
        cs = self.callsign_entry.get().strip().upper()
        valid, msg = validate_callsign(cs)
        if valid:
            self.settings.callsign = cs
            self.network.callsign = cs
            self.callsign_status.configure(text="✓", text_color=self.theme["text"])
        else:
            self.callsign_status.configure(text="✗", text_color="#FF6B6B")
        self.settings.save()

    def _save_target_ip(self):
        self.settings.target_ip = self.target_entry.get().strip()
        self.settings.save()

    def _save_port(self):
        try:
            p = int(self.port_entry.get().strip())
            self.settings.port = p
            self.settings.save()
        except ValueError: pass

    def _on_freq_change(self, v): self.settings.frequency = int(v); self.audio.frequency = int(v); self.settings.save()
    def _on_vol_change(self, v): self.settings.volume = v / 100.0; self.audio.volume = v / 100.0; self.settings.save()

    def _on_wpm_change(self, v):
        self.settings.wpm = int(v); self.audio.wpm = int(v)
        self.wpm_info.configure(text=f"1 dot = {1200/v:.0f} ms")
        if self.settings.auto_timing:
            self.settings.recompute_timing_from_wpm()
            self._refresh_timing_sliders()
        self.settings.save()

    def _on_dot_change(self, v): self.settings.dot_threshold = int(v); self.tap.update_timing(dot_threshold=int(v)); self.settings.save()
    def _on_letter_gap_change(self, v): self.settings.letter_gap = int(v); self.tap.update_timing(letter_gap=int(v)); self.settings.save()
    def _on_word_gap_change(self, v): self.settings.word_gap = int(v); self.tap.update_timing(word_gap=int(v)); self.settings.save()

    def _on_auto_timing_toggle(self):
        self.settings.auto_timing = self.auto_timing_var.get()
        if self.settings.auto_timing:
            self.settings.recompute_timing_from_wpm()
            self._refresh_timing_sliders()
        self.settings.save()

    def _refresh_timing_sliders(self):
        self.dot_slider.set(self.settings.dot_threshold)
        self._dot_slider_label.configure(text=f"{self.settings.dot_threshold} ms")
        self.letter_slider.set(self.settings.letter_gap)
        self._letter_slider_label.configure(text=f"{self.settings.letter_gap} ms")
        self.word_slider.set(self.settings.word_gap)
        self._word_slider_label.configure(text=f"{self.settings.word_gap} ms")
        self.tap.update_timing(self.settings.dot_threshold, self.settings.letter_gap, self.settings.word_gap)

    def _on_duration_change(self, v): self.settings.popup_duration = int(v); self.settings.save()
    def _on_check_change(self, attr, var): setattr(self.settings, attr, var.get()); self.settings.save()

    def _capture_key(self, target: str):
        btn = self.tap_key_btn if target == "tap" else self.bsp_key_btn
        btn.configure(text="Press any key…", fg_color=self.theme["accent"], text_color=self.theme["bg"])

        def on_captured(key_name: str):
            display = KeyboardHookManager.get_key_display_name(key_name)
            btn.configure(text=display, fg_color=self.theme["bg"], text_color=self.theme["text"])
            if target == "tap":
                self.settings.send_key = key_name
                self.kb.set_tap_key(key_name)
                if self.mini_window: self.mini_window.tap_indicator.configure(text=f"Hold {display} to tap")
            else:
                self.settings.backspace_key = key_name
                self.kb.set_backspace_key(key_name)
            self.settings.save()

        self.kb.capture_next_key(target, on_captured)

    def _on_msg_type(self, event=None):
        text = self.msg_entry.get()
        if text.strip():
            self.morse_preview.configure(text=MorseTranslator.encode(text))
        else:
            self.morse_preview.configure(text="")
        if not self._tap_mode_active:
            if text.strip(): self._start_auto_send_timer()
            else: self._stop_auto_send_timer()

    def _update_tap_display(self, morse: str):
        self.tap_display.configure(text=morse)
        if self.mini_window: self.mini_window._update_display(morse)
        if self._tap_mode_active:
            if morse.strip(): self._start_auto_send_timer()
            else: self._stop_auto_send_timer()

    def _start_auto_send_timer(self):
        if self._auto_send_after_id:
            self.after_cancel(self._auto_send_after_id)
            self._auto_send_after_id = None
        if self.auto_send_var.get():
            self._auto_send_start_time = time.monotonic()
            self._tick_auto_send()
        else:
            self.auto_send_progress.set(0)

    def _stop_auto_send_timer(self):
        if self._auto_send_after_id:
            self.after_cancel(self._auto_send_after_id)
            self._auto_send_after_id = None
        self.auto_send_progress.set(0)

    def _tick_auto_send(self):
        if not self.auto_send_var.get():
            self.auto_send_progress.set(0); return
        has_content = False
        if self._tap_mode_active:
            if self.tap.get_display_morse().strip(): has_content = True
        else:
            if self.msg_entry.get().strip(): has_content = True
        if not has_content:
            self.auto_send_progress.set(0); return

        elapsed = time.monotonic() - self._auto_send_start_time
        progress = elapsed / self.settings.auto_send_delay
        if progress >= 1.0:
            self.auto_send_progress.set(1.0)
            self._send_message()
        else:
            self.auto_send_progress.set(progress)
            self._auto_send_after_id = self.after(50, self._tick_auto_send)

    def _on_auto_send_toggle(self):
        self.settings.auto_send_enabled = self.auto_send_var.get()
        self.settings.save()
        if self.settings.auto_send_enabled: self._on_net_status("Auto-Send ON")
        else: self._on_net_status("Auto-Send OFF"); self._stop_auto_send_timer()
        self._on_msg_type()

    def _on_auto_delay_change(self, v):
        self.settings.auto_send_delay = int(v)
        self.auto_delay_label.configure(text=f"{int(v)}s")
        self.settings.save()
        self._on_msg_type()

    def _send_message(self):
        self._stop_auto_send_timer()
        if self._tap_mode_active:
            morse = self.tap.get_final_morse()
            text = self.tap.get_text()
            if not morse: self._on_net_status("Nothing to send."); return
        else:
            text = self.msg_entry.get().strip()
            if not text: self._on_net_status("Nothing to send."); return
            morse = MorseTranslator.encode(text)

        target = self.target_entry.get().strip()
        if not target: self._on_net_status("Send failed: No Target IP set!"); return
        cs = self.callsign_entry.get().strip().upper()
        valid, msg = validate_callsign(cs)
        if not valid: self._on_net_status(f"Send failed: {msg}"); return

        self._on_net_status(f"Attempting to send to {target}...")
        def do_send():
            success = self.network.send_message(target, morse, text)
            if success:
                msg_obj = MorseMessage(callsign=cs, morse=morse, text=text, timestamp=time.time(), direction="out")
                self.after(0, lambda: self._add_to_history(msg_obj))
                self.after(0, lambda: self._clear_message())
                self.after(0, lambda: self._on_net_status(f"Sent to {target}"))
            else:
                self.after(0, lambda: self._on_net_status(f"Failed to send to {target} (offline?)"))
        threading.Thread(target=do_send, daemon=True).start()

    def _clear_message(self):
        self._stop_auto_send_timer()
        self.msg_entry.delete(0, "end")
        self.morse_preview.configure(text="")
        self.tap_display.configure(text="")
        self.tap.reset()

    def _toggle_tap_mode(self):
        self._tap_mode_active = not self._tap_mode_active
        if self._tap_mode_active:
            self.tap.start()
            self.tap_btn.configure(text="⌨ Tap Mode: ON", fg_color=self.theme["accent"], text_color=self.theme["bg"])
            self._stop_auto_send_timer()
        else:
            self.tap.stop()
            self.audio.stop_tone()
            self.tap_btn.configure(text="⌨ Tap Mode: OFF", fg_color=self.theme["card_hover"], text_color=self.theme["text"])
            self.tap_key_btn.configure(fg_color=self.theme["bg"], text_color=self.theme["text"])

    def _update_key_status(self, pressed: bool):
        color = self.theme["accent"] if pressed else self.theme["faded"]
        text = "● transmitting" if pressed else "● idle"
        self.tap_key_status.configure(text=text, text_color=color)
        if self._tap_mode_active:
            if pressed:
                self.tap_key_btn.configure(fg_color=self.theme["accent"], text_color=self.theme["bg"])
            else:
                self.tap_key_btn.configure(fg_color=self.theme["bg"], text_color=self.theme["text"])
        if self.mini_window: self.mini_window._update_indicator(pressed)

    def _on_tap_key_down(self):
        if self._tap_mode_active: self.tap.on_key_down(); self.audio.start_tone()

    def _on_tap_key_up(self):
        if self._tap_mode_active: self.tap.on_key_up(); self.audio.stop_tone()

    def _on_bsp_key_down(self):
        if self._tap_mode_active:
            self.tap.on_backspace()
            # Visual feedback for backspace
            self.bsp_key_btn.configure(fg_color=self.theme["accent"], text_color=self.theme["bg"])
            self.after(150, lambda: self.bsp_key_btn.configure(fg_color=self.theme["bg"], text_color=self.theme["text"]))

    def _on_message_received(self, msg: dict):
        morse = msg.get("morse", ""); text = msg.get("text", MorseTranslator.decode(morse))
        callsign = msg.get("callsign", "???"); timestamp = msg.get("timestamp", time.time())
        my_cs = self.callsign_entry.get().strip().upper()
        conflict = (callsign.upper() == my_cs)
        msg_obj = MorseMessage(callsign=callsign, morse=morse, text=text, timestamp=timestamp, direction="in")
        self.after(0, lambda: self._add_to_history(msg_obj))
        if self.settings.show_popup:
            self.after(0, lambda: self._show_popup(callsign, morse, text, timestamp, conflict))
        if self.settings.play_audio:
            def on_char(i, c): self.after(0, lambda: self._highlight_popup_char(i))
            self.audio.play_morse_async(morse, self.settings.wpm, on_char_played=on_char)

    def _on_handshake(self, callsign: str, ip: str):
        my_cs = self.callsign_entry.get().strip().upper()
        if callsign.upper() == my_cs:
            self.after(0, lambda: messagebox.showwarning("Callsign Conflict", f"Peer '{callsign}' has the same callsign as you!\nPlease choose a different callsign."))
        self.after(0, lambda: self._on_net_status(f"Connected: {callsign} @ {ip}"))

    def _on_net_status(self, status: str):
        self.status_label.configure(text=status)
        if "Listening" in status or "Connected" in status or "Sent" in status or "ON" in status:
            self.status_dot.configure(text_color=self.theme["accent"])
        elif "Error" in status or "failed" in status or "Failed" in status or "Nothing" in status:
            self.status_dot.configure(text_color="#FF6B6B")
        else:
            self.status_dot.configure(text_color=self.theme["faded"])

    def _on_peer_discovered(self, callsign: str, ip: str, port: int):
        self.peers_label.configure(text=f"Found: {callsign} @ {ip}:{port}  (click to set)", text_color=self.theme["text"], cursor="hand2")
        self.peers_label.bind("<Button-1>", lambda e: self._select_peer(ip, callsign))

    def _select_peer(self, ip: str, callsign: str):
        self.target_entry.delete(0, "end"); self.target_entry.insert(0, ip); self._save_target_ip()

    _current_popup = None
    _current_popup_data = None

    def _show_popup(self, callsign: str, morse: str, text: str, timestamp: float, conflict: bool = False):
        if self._current_popup: self._current_popup.destroy(); self._current_popup = None
        from popup import MorsePopup
        popup = MorsePopup(settings=self.settings, theme=self.theme, on_repeat=lambda: self._repeat_popup_audio(morse), on_reply=lambda: self._reply_to_sender(callsign), on_close=lambda: setattr(self, "_current_popup", None))
        display_text = f"[CONFLICT] {text}" if conflict else text
        popup.show_message(callsign, morse, display_text, timestamp)
        self._current_popup = popup
        self._current_popup_data = (callsign, morse, text, timestamp)

    def _highlight_popup_char(self, index: int):
        if self._current_popup: self._current_popup.highlight_char(index)

    def _repeat_popup_audio(self, morse: str):
        if self.settings.play_audio: self.audio.play_morse_async(morse, self.settings.wpm)

    def _reply_to_sender(self, callsign: str):
        self.deiconify(); self.focus_force(); self.msg_entry.focus_set()

    def _add_to_history(self, msg: MorseMessage):
        self.settings.history.insert(0, msg.to_dict())
        self.settings.history = self.settings.history[:50]
        self.settings.save(); self._refresh_history()

    def _refresh_history(self):
        self.history_text.configure(state="normal"); self.history_text.delete("1.0", "end")
        for entry in self.settings.history:
            ts = datetime.fromtimestamp(entry.get("timestamp", 0)).strftime("%H:%M")
            cs = entry.get("callsign", "???"); direction = "→" if entry.get("direction") == "out" else "←"
            morse = entry.get("morse", ""); text = entry.get("text", "")
            line = f"[{ts}] {direction} {cs}: {morse}"
            if text: line += f"  ({text})"
            self.history_text.insert("end", line + "\n")
        self.history_text.configure(state="disabled")

    def _test_tone(self): self.audio.play_test_tone(300)

    def _toggle_listen(self):
        if self.network._running:
            self.network.stop_listening(); self.listen_btn.configure(text="Start Listen", fg_color=self.theme["card_hover"])
        else:
            self.network.callsign = self.callsign_entry.get().strip().upper()
            self.network.start_listening(self.settings.port)
            self.listen_btn.configure(text="Listening ●", fg_color=self.theme["accent"])

    def _refresh_status(self):
        if self.settings.auto_listen:
            self.network.callsign = self.callsign_entry.get().strip().upper()
            self.network.start_listening(self.settings.port)

    def _shrink_to_mini(self):
        self.withdraw()
        if self.mini_window is None or not self.mini_window.winfo_exists():
            self.mini_window = MiniWindow(self)
        self.mini_window.show()

    def _minimize_to_tray(self):
        self.withdraw(); self.app.show_tray_notification("MorseRelay", "Running in background")

    def _on_close(self):
        if self.settings.minimize_to_tray_on_close: self.withdraw()
        else: self.app.quit_app()

    def show_from_tray(self): self.deiconify(); self.focus_force()

    def _show_morse_chart(self):
        if self._chart_window is not None and self._chart_window.winfo_exists():
            self._chart_window.focus_force(); return
            
        self._chart_window = ctk.CTkToplevel(self)
        self._chart_window.title("Morse Code Chart")
        self._chart_window.geometry("500x600")
        self._chart_window.configure(fg_color=self.theme["bg"])
        self._chart_window.attributes("-topmost", True)
        
        ctk.CTkLabel(self._chart_window, text="International Morse Code", font=ctk.CTkFont(size=20, weight="bold"), text_color=self.theme["text"]).pack(pady=20)
        
        grid_frame = ctk.CTkFrame(self._chart_window, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        items = list(TEXT_TO_MORSE.items())
        for i, (char, morse) in enumerate(items):
            row = i % 12
            col = i // 12
            cell = ctk.CTkFrame(grid_frame, fg_color=self.theme["card"], corner_radius=8, border_width=1, border_color=self.theme["border"])
            cell.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            ctk.CTkLabel(cell, text=char, font=ctk.CTkFont(size=14, weight="bold"), text_color=self.theme["text"]).pack(side="left", padx=10, pady=8)
            ctk.CTkLabel(cell, text=morse, font=ctk.CTkFont(family="Consolas", size=14), text_color=self.theme["accent"]).pack(side="right", padx=10, pady=8)
            
        for c in range(4):
            grid_frame.grid_columnconfigure(c, weight=1)


class MiniWindow(ctk.CTkToplevel):
    TRANSPARENT = "#FF00FF"

    def __init__(self, dashboard: Dashboard):
        super().__init__()
        self.dashboard = dashboard
        self.settings = dashboard.settings
        self.theme = dashboard.theme
        self.tap = dashboard.tap

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        if sys.platform == "win32":
            self.configure(fg_color=self.TRANSPARENT)
            self.attributes("-transparentcolor", self.TRANSPARENT)
        else:
            self.configure(fg_color=self.theme["bg"])

        self.geometry("340x220+100+100")
        self._build_ui()
        self._enable_drag()

    def _build_ui(self):
        t = self.theme
        frame = ctk.CTkFrame(self, corner_radius=16, fg_color=t["card"], border_width=1, border_color=t["border"])
        frame.pack(fill="both", expand=True, padx=3, pady=3)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(header, text=self.settings.callsign, font=ctk.CTkFont(size=14, weight="bold"), text_color=t["text"]).pack(side="left")
        
        expand_btn = ctk.CTkLabel(header, text="⤢", font=ctk.CTkFont(size=18), cursor="hand2", text_color=t["secondary"])
        expand_btn.pack(side="right")
        expand_btn.bind("<Button-1>", lambda e: self._expand())

        ctk.CTkFrame(frame, fg_color=t["border"], height=1).pack(fill="x", padx=14, pady=2)

        self.morse_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(family="Consolas", size=18, weight="bold"), text_color=t["dot"], anchor="center", wraplength=300)
        self.morse_label.pack(fill="x", padx=14, pady=(10, 2))
        
        self.text_label = ctk.CTkLabel(frame, text="", font=ctk.CTkFont(family="Consolas", size=12), text_color=t["faded"], anchor="center")
        self.text_label.pack(fill="x", padx=14, pady=(0, 6))

        self.tap_indicator = ctk.CTkLabel(frame, text=f"Hold {KeyboardHookManager.get_key_display_name(self.settings.send_key)} to tap", font=ctk.CTkFont(size=11), text_color=t["secondary"])
        self.tap_indicator.pack(pady=2)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=14, pady=(2, 12))
        ctk.CTkButton(btn_frame, text="Send ▸", height=30, corner_radius=8, font=ctk.CTkFont(size=13, weight="bold"), fg_color=t["accent"], text_color=t["bg"], command=self._send).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(btn_frame, text="Clear", height=30, width=60, corner_radius=8, font=ctk.CTkFont(size=12), fg_color=t["card_hover"], text_color=t["text"], border_width=1, border_color=t["border"], command=self._clear).pack(side="left")

        self.tap.on_morse_updated = lambda m: self.after(0, lambda: self._update_display(m))
        self.tap.on_key_state = lambda p: self.after(0, lambda: self._update_indicator(p))

    def _update_display(self, morse: str):
        self.morse_label.configure(text=morse if morse else "—")
        if morse:
            self.text_label.configure(text=MorseTranslator.decode(morse))
        else: self.text_label.configure(text="")

    def _update_indicator(self, pressed: bool):
        if pressed:
            self.tap_indicator.configure(text="● transmitting", text_color=self.theme["accent"])
        else:
            self.tap_indicator.configure(text=f"Hold {KeyboardHookManager.get_key_display_name(self.settings.send_key)} to tap", text_color=self.theme["secondary"])

    def _send(self):
        self.dashboard._send_message()
        self._clear()

    def _clear(self):
        self.tap.reset(); self._update_display("")

    def _expand(self):
        self.hide(); self.dashboard.show_from_tray()

    def _enable_drag(self):
        def start(e): self._dx = e.x_root - self.winfo_x(); self._dy = e.y_root - self.winfo_y()
        def drag(e): self.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")
        self.bind("<ButtonPress-1>", start); self.bind("<B1-Motion>", drag)
        for child in self.winfo_children():
            child.bind("<ButtonPress-1>", start); child.bind("<B1-Motion>", drag)

    def show(self):
        self.deiconify(); self.update_idletasks()
        w, h = 346, 226; sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{sw-w-24}+{sh-h-64}")

    def hide(self): self.withdraw()