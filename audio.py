# audio.py
"""Audio engine for generating clean morse-code beeps and live side-tone."""

import threading
import numpy as np
import sounddevice as sd
import time
from typing import Optional, Callable


class AudioEngine:
    """Generates sine-wave beeps with smooth attack/release envelopes."""

    SAMPLE_RATE = 44100

    def __init__(self, frequency: int = 700, volume: float = 0.45, wpm: int = 20):
        self.frequency = frequency
        self.volume = volume
        self.wpm = wpm
        self._stop_flag = threading.Event()
        self._play_thread: Optional[threading.Thread] = None
        
        # Continuous tone state (for live side-tone when tapping)
        self._stream: Optional[sd.OutputStream] = None
        self._phase = 0.0

    def update(self, frequency=None, volume=None, wpm=None):
        if frequency is not None:
            self.frequency = max(200, min(2000, frequency))
        if volume is not None:
            self.volume = max(0.0, min(1.0, volume))
        if wpm is not None:
            self.wpm = max(5, min(40, wpm))

    # ── Live Continuous Tone (Sidetone) ────────────────────────
    def _audio_callback(self, outdata, frames, time_info, status):
        """Generates a continuous sine wave for the live stream."""
        t = (np.arange(frames) + self._phase) / self.SAMPLE_RATE
        outdata[:, 0] = self.volume * np.sin(2 * np.pi * self.frequency * t)
        self._phase = (self._phase + frames) % self.SAMPLE_RATE

    def start_tone(self):
        """Start playing a continuous beep (when Tap Key is pressed)."""
        if self._stream is None:
            try:
                self._stream = sd.OutputStream(
                    samplerate=self.SAMPLE_RATE, 
                    channels=1, 
                    dtype='float32',
                    callback=self._audio_callback
                )
                self._stream.start()
            except Exception:
                pass

    def stop_tone(self):
        """Stop the continuous beep (when Tap Key is released)."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            self._phase = 0.0

    # ── Pre-rendered Incoming Message Playback ─────────────────
    def _generate_beep(self, duration_ms: int) -> np.ndarray:
        """Generate a sine wave with smooth attack/release."""
        n = int(self.SAMPLE_RATE * duration_ms / 1000)
        if n <= 0:
            return np.zeros(0, dtype=np.float32)

        t = np.arange(n) / self.SAMPLE_RATE
        wave = np.sin(2 * np.pi * self.frequency * t)

        # 5 ms attack / 5 ms release to eliminate clicks
        attack = min(int(self.SAMPLE_RATE * 0.005), n // 2)
        release = min(int(self.SAMPLE_RATE * 0.005), n // 2)
        envelope = np.ones(n, dtype=np.float32)
        if attack > 0:
            envelope[:attack] = np.linspace(0, 1, attack, dtype=np.float32)
        if release > 0:
            envelope[-release:] = np.linspace(1, 0, release, dtype=np.float32)

        return (self.volume * envelope * wave).astype(np.float32)

    def _generate_silence(self, duration_ms: int) -> np.ndarray:
        n = int(self.SAMPLE_RATE * duration_ms / 1000)
        return np.zeros(n, dtype=np.float32)

    def _generate_morse_track(self, morse: str, wpm: int) -> np.ndarray:
        """Pre-render an entire morse string into one seamless audio array."""
        dot_ms = 1200.0 / wpm
        tracks = []
        
        for char in morse:
            if char == ".":
                tracks.append(self._generate_beep(int(dot_ms)))
                tracks.append(self._generate_silence(int(dot_ms)))
            elif char == "-":
                tracks.append(self._generate_beep(int(dot_ms * 3)))
                tracks.append(self._generate_silence(int(dot_ms)))
            elif char == " ":
                tracks.append(self._generate_silence(int(2 * dot_ms)))
            elif char == "/":
                tracks.append(self._generate_silence(int(4 * dot_ms)))
                
        if not tracks:
            return np.zeros(0, dtype=np.float32)
        
        # Concatenate all pieces into one perfectly seamless track
        return np.ascontiguousarray(np.concatenate(tracks))

    def play_morse_async(self, morse: str, wpm: int = None,
                         on_char_played: Callable = None,
                         on_done: Callable = None):
        """Play pre-rendered morse in a background thread."""
        self._stop_flag.set()
        if self._play_thread and self._play_thread.is_alive():
            self._play_thread.join(timeout=0.5)

        self._stop_flag.clear()
        self._play_thread = threading.Thread(
            target=self._play_wrapper,
            args=(morse, wpm, on_char_played, on_done),
            daemon=True
        )
        self._play_thread.start()

    def _play_wrapper(self, morse, wpm, on_char_played, on_done):
        try:
            if wpm is None:
                wpm = self.wpm
                
            track = self._generate_morse_track(morse, wpm)
            if len(track) == 0:
                if on_done:
                    on_done()
                return

            # Play the single seamless track
            sd.play(track, self.SAMPLE_RATE)
            
            # Sync UI highlighting with audio playback
            dot_ms = 1200.0 / wpm
            start_time = time.monotonic()
            elapsed_ms = 0.0
            
            for i, char in enumerate(morse):
                if self._stop_flag.is_set():
                    break
                    
                target_time = start_time + (elapsed_ms / 1000.0)
                sleep_needed = target_time - time.monotonic()
                if sleep_needed > 0:
                    time.sleep(sleep_needed)
                    
                if on_char_played and not self._stop_flag.is_set():
                    on_char_played(i, char)
                    
                if char == ".":
                    elapsed_ms += dot_ms * 2
                elif char == "-":
                    elapsed_ms += dot_ms * 4
                elif char == " ":
                    elapsed_ms += dot_ms * 2
                elif char == "/":
                    elapsed_ms += dot_ms * 4

            # Wait for audio to finish
            total_duration = len(track) / self.SAMPLE_RATE
            while (time.monotonic() - start_time) < total_duration and not self._stop_flag.is_set():
                time.sleep(0.05)
                
        except Exception:
            pass
        finally:
            if on_done:
                on_done()
            sd.stop()

    def stop(self):
        self._stop_flag.set()
        self.stop_tone()
        sd.stop()

    def play_test_tone(self, duration_ms=300):
        """Quick test beep."""
        def _play():
            wave = self._generate_beep(duration_ms)
            if len(wave) > 0:
                sd.play(wave, self.SAMPLE_RATE)
                sd.wait()
        threading.Thread(target=_play, daemon=True).start()