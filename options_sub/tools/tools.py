import cv2
import time

def save_snapshot(image, path_prefix="snapshot"):
    """vai guardar uma imagem com timestamp"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    fname = f"{path_prefix}_{ts}.jpg"
    cv2.imwrite(fname, image)
    print(f"[Tools] Snapshot salvo em {fname}")
    return fname