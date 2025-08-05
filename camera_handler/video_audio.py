import cv2
import pyaudio
import threading
import queue
import time
import numpy as np

class CameraStream:
    def __init__(self, camera_index, audio_index=None, debug=False):
        self.camera_index = camera_index
        self.audio_index = audio_index
        self.debug = debug

        self.cap = None
        self.audio_stream = None
        self.running = False

        self.video_queue = queue.Queue(maxsize=10)
        self.audio_queue = queue.Queue(maxsize=50)

        self.p = pyaudio.PyAudio()

        # Audio settings
        self.CHUNK = 1024
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 1
        self.RATE = 44100

    def start(self):
        # Start video
        self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if self.debug else 0)

        if not self.cap.isOpened():
            print(f"[Erro] Não foi possível abrir a câmera {self.camera_index}")
            return False

        # Start audio
        if self.audio_index is not None:
            try:
                self.audio_stream = self.p.open(format=self.FORMAT,
                                                channels=self.CHANNELS,
                                                rate=self.RATE,
                                                input=True,
                                                input_device_index=self.audio_index,
                                                frames_per_buffer=self.CHUNK)
            except Exception as e:
                print(f"[Aviso] Áudio não iniciado para câmera {self.camera_index}: {e}")

        self.running = True
        threading.Thread(target=self._update_video, daemon=True).start()
        threading.Thread(target=self._update_audio, daemon=True).start()
        return True

    def _update_video(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                if not self.video_queue.full():
                    self.video_queue.put(frame)
                if self.debug:
                    cv2.imshow(f"Camera {self.camera_index}", frame)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.stop()
                        break
            else:
                print(f"[Erro] Frame não capturado na câmera {self.camera_index}")
                self.stop()

    def _update_audio(self):
        while self.running and self.audio_stream is not None:
            try:
                data = self.audio_stream.read(self.CHUNK, exception_on_overflow=False)
                if not self.audio_queue.full():
                    self.audio_queue.put(data)
            except Exception as e:
                print(f"[Erro Áudio] Câmera {self.camera_index}: {e}")
                break

    def get_latest_frame(self):
        if not self.video_queue.empty():
            return self.video_queue.get()
        return None

    def get_latest_audio(self):
        if not self.audio_queue.empty():
            return self.audio_queue.get()
        return None

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        if self.debug:
            cv2.destroyAllWindows()
        self.p.terminate()

# Função para iniciar múltiplas câmeras
def start_all_cameras(max_cameras=4, debug=False):
    streams = []
    for i in range(max_cameras):
        cam = CameraStream(camera_index=i, audio_index=i, debug=debug)
        success = cam.start()
        if success:
            print(f"[Info] Câmera {i} iniciada com sucesso.")
            streams.append(cam)
        else:
            print(f"[Aviso] Ignorando câmera {i}.")
    return streams
