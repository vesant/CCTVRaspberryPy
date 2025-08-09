import socket
import struct
import threading
import queue
import time
import zlib
import cv2

# Uso de protocolo: cabeçalho fixo + JPEG
# MAGIC(8) | VER(1) | CAM(1) | TS(8, double) | SIZE(4, uint32) | PAYLOAD
MAGIC = b'EVOLCCTV'
VERSION = 1

def _now():
    return time.time()

class DataTX:
    """
    vai gerar um cliente de envio de vídeo via TCP (reliable)
    envia frames codificados em JPEG
    reconnection automática 
    thread própria, interface com queue
    """
    def __init__(self, server_host, server_port, *, jpeg_quality=70, queue_size=100, debug=True, connect_timeout=5):
        self.server_host = server_host
        self.server_port = int(server_port)
        self.jpeg_quality = int(jpeg_quality)
        self.debug = bool(debug)
        self.connect_timeout = int(connect_timeout)

        self._sock = None
        self._sender = None
        self._running = False
        self._q = queue.Queue(maxsize=queue_size)

    def _dbg(self, msg):
        if self.debug:
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [DataTX] {msg}", flush=True)

    def start(self):
        self._running = True
        self._sender = threading.Thread(target=self._loop, daemon=True)
        self._sender.start()

    def stop(self):
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass

    def _connect(self):
        while self._running:
            try:
                self._dbg(f"A ligar a {self.server_host}:{self.server_port}...")
                s = socket.create_connection((self.server_host, self.server_port), timeout=self.connect_timeout)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._sock = s
                self._dbg("Ligado.")
                return True
            except Exception as e:
                self._dbg(f"Falha de ligação: {e}. A tentar de novo em 3s.")
                time.sleep(3)
        return False

    def _send_packet(self, cam_id, ts, jpg_bytes):
        header = MAGIC + bytes([VERSION, cam_id & 0xFF]) + struct.pack("!dI", float(ts), len(jpg_bytes))
        # opcional checksum CRC32 no fim (pode ser util no servidor)
        crc = struct.pack("!I", zlib.crc32(jpg_bytes) & 0xFFFFFFFF)
        payload = header + jpg_bytes + crc
        totalsent = 0
        while totalsent < len(payload):
            sent = self._sock.send(payload[totalsent:])
            if sent == 0:
                raise RuntimeError("socket connection broken")
            totalsent += sent

    def _loop(self):
        # vai tentar conectar e enviar enquanto _running
        while self._running:
            if self._sock is None:
                if not self._connect():
                    break
            try:
                cam_id, frame, ts = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            # encode JPEG
            try:
                ok, enc = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality])
                if not ok:
                    self._dbg("Falha a encode JPEG; frame descartado.")
                    continue
                self._send_packet(cam_id, ts, enc.tobytes())
            except (BrokenPipeError, ConnectionResetError, OSError) as e:
                self._dbg(f"Ligação perdida: {e}. Reconectando...")
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                time.sleep(1)
            except Exception as e:
                self._dbg(f"Erro a enviar frame: {e}")

        self._dbg("Loop de envio terminado.")

    def send_frame(self, cam_id: int, frame):
        """forma uma "fila" de frames para envio (non-blocking)"""
        if not self._running:
            return
        ts = _now()
        try:
            # drop se cheio (tempo-real)
            if self._q.full():
                _ = self._q.get_nowait()
            self._q.put_nowait((int(cam_id), frame, ts))
        except Exception:
            pass