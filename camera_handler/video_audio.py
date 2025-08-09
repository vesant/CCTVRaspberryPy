import cv2
import platform
import threading
import time
import numpy as np

try:
    import pyaudio
except Exception:
    pyaudio = None

def _dbg(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def _backend_code(name: str) -> int:
    name = (name or "auto").lower()
    # nem todas as builds têm todas as constantes; usa getattr com fallback 0
    MAP = {
        "auto": 0,
        "any": 0,
        "dshow": getattr(cv2, "CAP_DSHOW", 0),
        "msmf": getattr(cv2, "CAP_MSMF", 0),
        "v4l2": getattr(cv2, "CAP_V4L2", 0),
    }
    return MAP.get(name, 0)

class CameraStream:
    """
    vai fazer captura de camara com thread
    mantem SEMPRE o último frame (anti-flicker)
    backend configuravel por camara (dshow/msmf/v4l2/auto) 
    opcional: forçar MJPG
    """
    def __init__(self, camera_index: int, *, width=None, height=None, fps=None,
                 backend: str = None, force_mjpg: bool = False,
                 audio_index=None, enable_audio=False, debug=False):
        self.camera_index = int(camera_index)
        self.width = width
        self.height = height
        self.fps = fps
        self.backend = backend
        self.force_mjpg = bool(force_mjpg)

        self.audio_index = audio_index
        self.enable_audio = enable_audio and (pyaudio is not None)
        self.debug = bool(debug)

        self.cap = None
        self.running = False

        # ultimo frame persistente
        self._last_frame = None
        self._lock = threading.Lock()

        # métricas
        self._frame_count = 0
        self._fps_est = 0.0
        self._t0 = 0.0

        # audio (opcional)
        if self.enable_audio and pyaudio is not None:
            self._pa = pyaudio.PyAudio()
            self.CHUNK = 1024
            self.FORMAT = pyaudio.paInt16
            self.CHANNELS = 1
            self.RATE = 16000
            self.audio_stream = None
        else:
            self._pa = None
            self.audio_stream = None

    def start(self) -> bool:
        # backend default por SO
        if self.backend is None:
            if platform.system() == "Windows":
                self.backend = "dshow"
            elif platform.system() == "Linux":
                self.backend = "v4l2"
            else:
                self.backend = "auto"

        backend_code = _backend_code(self.backend)
        _dbg(f"[Init] A abrir camara {self.camera_index} (backend={self.backend}/{backend_code})")
        self.cap = cv2.VideoCapture(self.camera_index, backend_code)

        if not self.cap or not self.cap.isOpened():
            _dbg(f"[Error] Não foi possível abrir a camara {self.camera_index} com backend {self.backend}")
            return False

        # tentar reduzir buffers (menos lag/flicker quando suportado)
        try:
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        # opcional: forçar MJPG (muitas USB em Windows ficam estáveis)
        if self.force_mjpg:
            try:
                fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            except Exception:
                pass

        if self.width:  self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  int(self.width))
        if self.height: self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
        if self.fps:    self.cap.set(cv2.CAP_PROP_FPS,         float(self.fps))

        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_reported = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        _dbg(f"[Info] C{self.camera_index}: {w}x{h} @ ~{fps_reported:.1f} fps (backend={self.backend})")

        # audio opcional
        if self.enable_audio and self._pa is not None:
            try:
                self.audio_stream = self._pa.open(format=self.FORMAT, channels=self.CHANNELS, rate=self.RATE,
                                                  input=True, input_device_index=self.audio_index,
                                                  frames_per_buffer=self.CHUNK)
                _dbg(f"[Info] Áudio ligado para C{self.camera_index} (idx={self.audio_index})")
            except Exception as e:
                _dbg(f"[Aviso] Áudio indisponível para C{self.camera_index}: {e}")
                self.audio_stream = None

        self.running = True
        self._t0 = time.time()
        threading.Thread(target=self._video_loop, daemon=True).start()
        if self.audio_stream is not None:
            threading.Thread(target=self._audio_loop, daemon=True).start()
        return True

    def _video_loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                # nao matar a stream (algumas camaras dao falso negativo pontual)
                time.sleep(0.01)
                continue

            with self._lock:
                self._last_frame = frame

            self._frame_count += 1
            if self._frame_count % 20 == 0:
                now = time.time()
                dt = now - self._t0
                if dt > 0:
                    self._fps_est = 20.0 / dt
                self._t0 = now

        _dbg(f"[Stop] Loop de video interrompido C{self.camera_index}")

    def _audio_loop(self):
        while self.running and self.audio_stream is not None:
            try:
                _ = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
            except Exception as e:
                _dbg(f"[Error 'audio'] C{self.camera_index}: {e}")
                break
        _dbg(f"[Stop] Loop de audio interrompido C{self.camera_index}")

    def get_frame(self):
        with self._lock:
            return None if self._last_frame is None else self._last_frame.copy()

    def fps_estimate(self) -> float:
        return float(self._fps_est)

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            if self.cap: self.cap.release()
        except Exception:
            pass
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
        except Exception:
            pass
        if self._pa is not None:
            try: self._pa.terminate()
            except Exception: pass
        _dbg(f"[Stop] Camara {self.camera_index} encerrada.")

class MultiCamManager:
    def __init__(self, *, device_indices=None, backends=None, max_cameras=4,
                 width=None, height=None, fps=None, force_mjpg=False,
                 enable_audio=False, debug=False):
        """
        device_indices: lista de índices (ex.: [0,1,2,3]); se None -> range(max_cameras)
        backends: lista com 'dshow'/'msmf'/'v4l2'/'auto' por slot; se None -> default por SO
        """
        self.max_cameras = int(max_cameras)
        self.device_indices = device_indices or list(range(self.max_cameras))
        self.backends = backends or [None]*self.max_cameras
        self.streams = []
        self.enable_audio = enable_audio
        self.width = width
        self.height = height
        self.fps = fps
        self.force_mjpg = force_mjpg
        self.debug = debug

        # normalizar tamanhos
        if len(self.device_indices) < self.max_cameras:
            self.device_indices += list(range(self.max_cameras - len(self.device_indices)))
        if len(self.backends) < self.max_cameras:
            self.backends += [None] * (self.max_cameras - len(self.backends))

    def start_all(self):
        self.streams = []
        for slot in range(self.max_cameras):
            dev = self.device_indices[slot]
            be  = self.backends[slot]
            s = CameraStream(dev, width=self.width, height=self.height, fps=self.fps,
                             backend=be, force_mjpg=self.force_mjpg,
                             audio_index=dev, enable_audio=self.enable_audio, debug=self.debug)
            if s.start():
                self.streams.append(s)
            else:
                self.streams.append(None)
        return self.streams

    def get_frames(self):
        frames = []
        for s in self.streams:
            frames.append(None if s is None else s.get_frame())
        return frames

    def stop_all(self):
        for s in self.streams:
            if s is not None:
                s.stop()

def make_grid_2x2(frames, tile_size=(640, 360), text_overlay=True):
    tw, th = int(tile_size[0]), int(tile_size[1])
    canvas = np.zeros((th*2, tw*2, 3), dtype=np.uint8)
    for i in range(4):
        r, c = i // 2, i % 2
        x0, y0 = c*tw, r*th
        frm = frames[i] if i < len(frames) else None
        if frm is not None:
            h, w = frm.shape[:2]
            scale = min(tw / w, th / h)
            nw, nh = int(w*scale), int(h*scale)
            resized = cv2.resize(frm, (nw, nh), interpolation=cv2.INTER_AREA)
            xoff = x0 + (tw - nw)//2
            yoff = y0 + (th - nh)//2
            canvas[yoff:yoff+nh, xoff:xoff+nw] = resized
        cv2.rectangle(canvas, (x0, y0), (x0+tw-1, y0+th-1), (60,60,60), 1)
        if text_overlay:
            label = f"C{i} {'OK' if frm is not None else 'OFF'}"
            cv2.putText(canvas, label, (x0+10, y0+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (0,255,255) if frm is not None else (0,0,255), 2, cv2.LINE_AA)
    return canvas
