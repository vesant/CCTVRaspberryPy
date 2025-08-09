#!/usr/bin/env python3
import argparse
import os
import platform
import subprocess
import sys
import time

try:
    import cv2
except Exception as e:
    print("Precisas do OpenCV (opencv-python / python3-opencv). Erro:", e)
    sys.exit(1)

# Map de nomes -> códigos OpenCV
BACKENDS = {
    "auto": 0,
    "dshow": getattr(cv2, "CAP_DSHOW", 0),
    "msmf": getattr(cv2, "CAP_MSMF", 0),
    "v4l2": getattr(cv2, "CAP_V4L2", 0),
}

def try_open(idx, backend_name, width, height, fps, try_mjpg):
    """Tenta abrir uma câmara com backend e definições. Devolve (ok, backend_usado)."""
    code = BACKENDS.get(backend_name, 0)
    cap = cv2.VideoCapture(idx, code)
    if not cap or not cap.isOpened():
        return False, None

    # reduzir buffer se der (menos lag/flicker)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    # tentar MJPG quando pedido (muitas USB no Windows ficam estáveis)
    if try_mjpg:
        try:
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        except Exception:
            pass

    # ajustar propriedades alvo (nem todas aceitam)
    if width:  cap.set(cv2.CAP_PROP_FRAME_WIDTH,  int(width))
    if height: cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(height))
    if fps:    cap.set(cv2.CAP_PROP_FPS,         float(fps))

    # warm-up + tentativa de leitura
    ok, frame = cap.read()
    tries = 0
    while (not ok or frame is None) and tries < 5:
        time.sleep(0.03)
        ok, frame = cap.read()
        tries += 1

    cap.release()
    return (ok and frame is not None), backend_name if (ok and frame is not None) else (False, None)


def detect_cameras(max_devs, max_index, width, height, fps, force_mjpg_default):
    """Percorre índices até max_index e recolhe até max_devs câmaras funcionais."""
    os_name = platform.system()
    if os_name == "Windows":
        order = ["dshow", "msmf"]
        force_mjpg = True if force_mjpg_default is None else force_mjpg_default
    elif os_name == "Linux":
        order = ["v4l2", "auto"]
        force_mjpg = False if force_mjpg_default is None else force_mjpg_default
    else:
        order = ["auto"]
        force_mjpg = False if force_mjpg_default is None else force_mjpg_default

    found_devs = []
    found_bes  = []

    print(f"[auto] SO={os_name} | ordem backends={order} | force_mjpg={force_mjpg}")
    for idx in range(max_index + 1):
        if len(found_devs) >= max_devs:
            break
        # tenta em ordem; escolhe o primeiro que der imagem
        chosen_be = None
        for be in order:
            ok, used = try_open(idx, be, width, height, fps, try_mjpg=force_mjpg)
            if ok:
                chosen_be = used
                break