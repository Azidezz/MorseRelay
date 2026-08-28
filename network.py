# network.py
"""TCP messaging + UDP peer discovery."""

import socket
import json
import threading
import time
from typing import Callable, Optional

class NetworkManager:
    def __init__(self, callsign: str = "NODE01", port: int = 7777):
        self.callsign = callsign
        self.port = port
        self._running = False
        self._listen_sock: Optional[socket.socket] = None
        self._udp_sock: Optional[socket.socket] = None
        self._connections: dict[str, socket.socket] = {}
        self.on_message_received: Optional[Callable[[dict], None]] = None
        self.on_handshake: Optional[Callable[[str, str], None]] = None
        self.on_status: Optional[Callable[[str], None]] = None
        self.on_peer_discovered: Optional[Callable[[str, str, int], None]] = None

    def start_listening(self, port: int = None):
        if port: self.port = port
        self._running = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._discovery_loop, daemon=True).start()
        if self.on_status: self.on_status(f"Listening on port {self.port}")

    def stop_listening(self):
        self._running = False
        if self._listen_sock:
            try: self._listen_sock.close()
            except OSError: pass
        if self._udp_sock:
            try: self._udp_sock.close()
            except OSError: pass
        for cs, sock in list(self._connections.items()):
            try: sock.close()
            except OSError: pass
        self._connections.clear()
        if self.on_status: self.on_status("Stopped")

    def _listen_loop(self):
        try:
            self._listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._listen_sock.bind(("0.0.0.0", self.port))
            self._listen_sock.listen(5)
            self._listen_sock.settimeout(1.0)
            while self._running:
                try:
                    conn, addr = self._listen_sock.accept()
                    threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
                except socket.timeout: continue
                except OSError: break
        except OSError as e:
            if self.on_status: self.on_status(f"Listen error: {e}")

    def _handle_client(self, conn: socket.socket, addr):
        peer_ip = addr[0]
        buffer = b""
        try:
            while self._running:
                chunk = conn.recv(4096)
                if not chunk: break
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        msg = json.loads(line.decode("utf-8"))
                        self._process_message(msg, conn, peer_ip)
                    except (json.JSONDecodeError, UnicodeDecodeError): pass
        except OSError: pass
        finally: conn.close()

    def _process_message(self, msg: dict, conn: socket.socket, peer_ip: str):
        mtype = msg.get("type", "")
        if mtype == "handshake":
            cs = msg.get("callsign", "???")
            self._connections[cs] = conn
            if self.on_handshake: self.on_handshake(cs, peer_ip)
            self._send(conn, {"type": "handshake_ack", "callsign": self.callsign})
        elif mtype == "handshake_ack":
            cs = msg.get("callsign", "???")
            self._connections[cs] = conn
            if self.on_handshake: self.on_handshake(cs, peer_ip)
        elif mtype == "morse":
            if self.on_message_received: self.on_message_received(msg)
            self._send(conn, {"type": "ack", "timestamp": msg.get("timestamp")})
        elif mtype == "disconnect":
            cs = msg.get("callsign", "")
            self._connections.pop(cs, None)

    def send_message(self, target_ip: str, morse: str, text: str) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((target_ip, self.port))
            self._send(sock, {"type": "handshake", "callsign": self.callsign, "version": "1.0"})
            self._send(sock, {"type": "morse", "callsign": self.callsign, "morse": morse, "text": text, "timestamp": time.time()})
            self._send(sock, {"type": "disconnect", "callsign": self.callsign})
            sock.close()
            if self.on_status: self.on_status(f"Sent to {target_ip}")
            return True
        except Exception as e:
            if self.on_status: self.on_status(f"Send failed: {e}")
            return False

    def _send(self, sock: socket.socket, data: dict):
        try: sock.sendall((json.dumps(data) + "\n").encode("utf-8"))
        except OSError: pass

    def _discovery_loop(self):
        try:
            self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._udp_sock.bind(("0.0.0.0", self.port + 1))
            self._udp_sock.settimeout(2.0)
            announce = json.dumps({"type": "discovery", "callsign": self.callsign, "port": self.port}).encode("utf-8")
            last_broadcast = 0.0
            while self._running:
                now = time.time()
                if now - last_broadcast > 5.0:
                    try: self._udp_sock.sendto(announce, ("255.255.255.255", self.port + 1))
                    except OSError: pass
                    last_broadcast = now
                try:
                    data, addr = self._udp_sock.recvfrom(4096)
                    msg = json.loads(data.decode("utf-8"))
                    if msg.get("type") == "discovery" and msg.get("callsign") != self.callsign:
                        if self.on_peer_discovered: self.on_peer_discovered(msg["callsign"], addr[0], msg.get("port", 7777))
                except socket.timeout: continue
                except (OSError, json.JSONDecodeError): continue
        except OSError: pass

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError: return "127.0.0.1"