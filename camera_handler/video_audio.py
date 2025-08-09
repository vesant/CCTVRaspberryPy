import cv2
import platform
import threading
import queue
import time
import numpy as np

try:
    import pyaudio
except Exception:  # torna o áudio opcional (útil no Raspberry sem PyAudio)
    pyaudio = None

# log simples
def _dbg(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

class CameraStream:
    """
    fluxo que faz a câmara USB com thread própria (vídeo + áudio opcional).
    é universal! funciona em Windows e Linux! (será que funciona no Mac?)
    """
    def __init__(self, camera_index: int, *, width=None, height=None, fps=None,
                 audio_index=None, enable_audio=False, debug=False):
        self.camera_index = int(camera_index)
        self.width = width
        self.height = height
        self.fps = fps
        self.audio_index = audio_index
        self.enable_audio = enable_audio and (pyaudio is not None)
        self.debug = bool(debug)

        self.cap = None
        self._video_thread = None
        self._audio_thread = None
        self.running = False

        self.video_queue = queue.Queue(maxsize=2)  # só o frame mais recente
        self.audio_queue = queue.Queue(maxsize=20)

        # estado de métricas
        self._frame_count = 0
        self._fps_est = 0.0
        self._t0 = 0.0

        # áudio (opcional)
        if self.enable_audio and pyaudio is not None:
            self._pa = pyaudio.PyAudio()
            self.CHUNK = 1024
            self.FORMAT = pyaudio.paInt16
            self.CHANNELS = 1
            self.RATE = 16000  # mais leve para o Raspberry (devido a ser 32bit)
            self.audio_stream = None
        else:
            self._pa = None
            self.audio_stream = None

    def start(self) -> bool:
        """inicia threads"""
        backend = 0
        if platform.system() == "Windows" and self.debug:
            # no Windows, CAP_DSHOW reduz latência e evita warnings de MSMF em algumas webcams
            backend = cv2.CAP_DSHOW

        _dbg(f"[Init]A abrir camara... {self.camera_index} (backend={backend})")
        self.cap = cv2.VideoCapture(self.camera_index, backend)

        if not self.cap or not self.cap.isOpened():
            _dbg(f"[Error] Não foi possível abrir e/ou encontrar uma camara! {self.camera_index}")
            return False

        # tenta aplicar propriedades (se ouvert support)
        if self.width:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
        if self.height:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
        if self.fps:
            self.cap.set(cv2.CAP_PROP_FPS, float(self.fps))

        # vai ler o estado apos ajustes
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_reported = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        _dbg(f"[Info] C{self.camera_index}: {w}x{h} @ ~{fps_reported:.1f} fps")

        # se a camera tiver microfone, vai capturar aqui
        if self.enable_audio and self._pa is not None:
            try:
                self.audio_stream = self._pa.open(format=self.FORMAT,
                                                  channels=self.CHANNELS,
                                                  rate=self.RATE,
                                                  input=True,
                                                  input_device_index=self.audio_index,
                                                  frames_per_buffer=self.CHUNK)
                _dbg(f"[Info] Audio ligado para C{self.camera_index} (idx={self.audio_index})")
            except Exception as e:
                _dbg(f"[Error] Audio indisponível para C{self.camera_index}: {e}")
                self.audio_stream = None

        self.running = True
        self._t0 = time.time()

        self._video_thread = threading.Thread(target=self._video_loop, daemon=True)
        self._video_thread.start()

        if self.audio_stream is not None:
            self._audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._audio_thread.start()

        return True

    def _video_loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                _dbg(f"[Error] Não é possivel capturar frame em C{self.camera_index}")
                time.sleep(0.1)
                continue

            # manter apenas o frame mais recente
            if not self.video_queue.empty():
                try:
                    self.video_queue.get_nowait()
                except Exception:
                    pass
            try:
                self.video_queue.put_nowait(frame)
            except Exception:
                pass

            # fps estimado (a cada 20 frames)
            self._frame_count += 1
            if self._frame_count % 20 == 0:
                now = time.time()
                dt = now - self._t0
                if dt > 0:
                    self._fps_est = 20.0 / dt
                self._t0 = now

        _dbg(f"[Stop] Video interrompido em C{self.camera_index}")

    def _audio_loop(self):
        while self.running and self.audio_stream is not None:
            try:
                data = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
                if not self.audio_queue.full():
                    self.audio_queue.put_nowait(data)
            except Exception as e:
                _dbg(f"[Error 'audio'] C{self.camera_index}: {e}")
                break
        _dbg(f"[Stop] Audio interrompido em C{self.camera_index}")

    def get_frame(self):
        """tenta obter o frame mais recente (ou None)"""
        if self.video_queue.empty():
            return None
        try:
            return self.video_queue.get_nowait()
        except Exception:
            return None

    def get_audio_chunk(self):
        if self.audio_queue.empty():
            return None
        try:
            return self.audio_queue.get_nowait()
        except Exception:
            return None

    def fps_estimate(self) -> float:
        return float(self._fps_est)

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            if self.cap:
                self.cap.release()
        except Exception:
            pass
        try:
            if self.audio_stream:
                self.audio_stream.stop_stream()
                self.audio_stream.close()
        except Exception:
            pass
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
        _dbg(f"[Stop] Câmara {self.camera_index} desligada.")

class MultiCamManager:
    """
    aceita até 4 camaras. serve para o main e para o envio de frames
    """
    def __init__(self, max_cameras=4, *, width=None, height=None, fps=None, enable_audio=False, debug=False):
        self.max_cameras = int(max_cameras)
        self.streams = []
        self.enable_audio = enable_audio
        self.width = width
        self.height = height
        self.fps = fps
        self.debug = debug

    def start_all(self):
        self.streams = []
        for idx in range(self.max_cameras):
            s = CameraStream(idx, width=self.width, height=self.height, fps=self.fps,
                             audio_index=idx, enable_audio=self.enable_audio, debug=self.debug)
            if s.start():
                self.streams.append(s)
            else:
                # manter o slot vazio para preservar layout 2x2
                self.streams.append(None)
        return self.streams

    def get_frames(self):
        """
        vai devolver lista com o último frame de cada slot (None quando indisponível)
        """
        frames = []
        for s in self.streams:
            if s is None:
                frames.append(None)
            else:
                frames.append(s.get_frame())
        return frames

    def stop_all(self):
        for s in self.streams:
            if s is not None:
                s.stop()

def make_grid_2x2(frames, tile_size=(640, 360), text_overlay=True):
    """
    vai receber lista de até 4 frames e devolve imagem 2x2
    se o frame é None, o tile fica preto!
    """
    tw, th = int(tile_size[0]), int(tile_size[1])
    canvas = np.zeros((th*2, tw*2, 3), dtype=np.uint8)

    for i in range(4):
        r = i // 2
        c = i % 2
        x0, y0 = c*tw, r*th
        frm = frames[i] if i < len(frames) else None

        if frm is not None:
            h, w = frm.shape[:2]
            scale = min(tw / w, th / h)
            nw, nh = int(w*scale), int(h*scale)
            resized = cv2.resize(frm, (nw, nh), interpolation=cv2.INTER_AREA)
            # centralizar dentro do tile
            xoff = x0 + (tw - nw)//2
            yoff = y0 + (th - nh)//2
            canvas[yoff:yoff+nh, xoff:xoff+nw] = resized
        # borda fina para cada tile
        cv2.rectangle(canvas, (x0, y0), (x0+tw-1, y0+th-1), (60,60,60), 1)
        if text_overlay:
            label = f"C{i} {'OK' if frm is not None else 'OFF'}"
            cv2.putText(canvas, label, (x0+10, y0+24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255) if frm is not None else (0,0,255), 2, cv2.LINE_AA)
    return canvas