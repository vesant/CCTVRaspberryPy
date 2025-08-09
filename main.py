import cv2
import time
import argparse
import os

from camera_handler.video_audio import MultiCamManager, make_grid_2x2
from options_sub.subMain import SubConsole
from options_sub.tools.tools import save_snapshot
from core.dataTX import DataTX

def parse_args():
    ap = argparse.ArgumentParser(description="CCTV 2x2 para Raspberry/Windows")
    ap.add_argument("--cams", type=int, default=4, help="Numero maximo de camaras (ate 4)")
    ap.add_argument("--width", type=int, default=640, help="Largura alvo por câmara")
    ap.add_argument("--height", type=int, default=360, help="Altura alvo por câmara")
    ap.add_argument("--fps", type=int, default=15, help="FPS alvo por câmara")
    ap.add_argument("--server", type=str, default=None, help="IP/host do servidor (opcional)")
    ap.add_argument("--port", type=int, default=5050, help="Porta do servidor")
    ap.add_argument("--quality", type=int, default=70, help="Qualidade JPEG (envio)")
    ap.add_argument("--debug", action="store_true", help="Logs detalhados")
    return ap.parse_args()

def main():
    args = parse_args()

    # 1 
    # Camaras
    m = MultiCamManager(max_cameras=min(4, args.cams),
                        width=args.width, height=args.height, fps=args.fps,
                        #enable_audio=False, # audio desativado por padrão, ativar se necessário
                        enable_audio=True,
                        debug=args.debug)
    streams = m.start_all()

    # 2 
    # Networking (inicialmente desligado até o utilizador ligar no menu)
    tx = None
    tx_enabled = False

    if args.server:
        tx = DataTX(args.server, args.port, jpeg_quality=args.quality, debug=True)
        # não inicia ja; fica a espera do toggle

    # 3
    # SubMenu (consola)
    fullscreen = True
    window = "CCTV"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)

    def toggle_fullscreen():
        nonlocal fullscreen
        fullscreen = not fullscreen
        cv2.setWindowProperty(window, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN if fullscreen else cv2.WINDOW_NORMAL)
        print(f"[Main] Fullscreen: {fullscreen}")

    def toggle_tx():
        nonlocal tx_enabled, tx
        if tx is None:
            if args.server:
                tx = DataTX(args.server, args.port, jpeg_quality=args.quality, debug=True)
            else:
                print("[Main] Sem servidor configurado (--server)...")
                return
        if not tx_enabled:
            tx.start()
            tx_enabled = True
            print("[Main] Transmissão para server: LIGADA!")
        else:
            tx.stop()
            tx_enabled = False
            print("[Main] Transmissão para server: DESLIGADA!")

    def do_snapshot():
        # faz a snapshot
        grid = last_grid.copy() if last_grid is not None else None
        if grid is None:
            print("[Main] Sem imagem para guardar...")
            return
        save_snapshot(grid, path_prefix="cctv_grid")

    def reload_cams():
        print("[Main] A recarregar camaras...")
        m.stop_all()
        time.sleep(0.5)
        m.start_all()

    def do_quit():
        nonlocal running
        running = False

    menu = SubConsole(on_toggle_fullscreen=toggle_fullscreen,
                      on_toggle_tx=toggle_tx,
                      on_snapshot=do_snapshot,
                      on_reload_cams=reload_cams,
                      on_quit=do_quit)
    menu.start()

    # 4 
    # Loop de UI
    running = True
    last_grid = None
    tile_size = (args.width, args.height)

    print("[Main] Controlo rapido: 'f' fullscreen, 't' TX (Transmitir), 's' snapshot, 'q' sair.")
    while running:
        frames = m.get_frames()
        # enviar frames (se ativo)
        if tx_enabled and tx is not None:
            for cam_id, frm in enumerate(frames):
                if frm is not None:
                    tx.send_frame(cam_id, frm)

        # compor grid para visualização
        # garantir tamanho de 4 slots
        while len(frames) < 4:
            frames.append(None)
        grid = make_grid_2x2(frames, tile_size=tile_size, text_overlay=True)
        last_grid = grid

        cv2.imshow(window, grid)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            running = False
        elif key == ord('f'):
            toggle_fullscreen()
        elif key == ord('t'):
            toggle_tx()
        elif key == ord('s'):
            do_snapshot()

    # 5) Shutdown
    print("[Main] A encerrar...")
    if tx is not None:
        tx.stop()
    m.stop_all()
    cv2.destroyAllWindows()
    print("[Main] Terminado.")

if __name__ == "__main__":
    main()