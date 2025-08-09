import threading
import time

class SubConsole:
    """
    cria menu na consola minimalista a correr em thread própria
    interage com 'main.py' através de callbacks
    """
    def __init__(self, *, on_toggle_fullscreen, on_toggle_tx, on_snapshot, on_reload_cams, on_quit):
        self.on_toggle_fullscreen = on_toggle_fullscreen
        self.on_toggle_tx = on_toggle_tx
        self.on_snapshot = on_snapshot
        self.on_reload_cams = on_reload_cams
        self.on_quit = on_quit

        self._thr = None
        self._running = False

    def start(self):
        if self._running:
            return
        self._running = True
        self._thr = threading.Thread(target=self._loop, daemon=True)
        self._thr.start()

    def stop(self):
        self._running = False

    def _print_menu(self):
        print("\nx=============x SubMenu CCTV x=============x")
        print("[F] - Alternar Fullscreen")
        print("[T] - Ligar/Desligar transmissão para servidor")
        print("[S] - Guardar snapshot (grid)")
        print("[R] - Recarregar câmaras")
        print("[Q] - Sair")
        print("x============================================x")

    def _loop(self):
        self._print_menu()
        while self._running:
            try:
                cmd = input("> ").strip().lower()
            except EOFError:
                break
            if not cmd:
                continue
            c = cmd[0]
            if c == 'f':
                self.on_toggle_fullscreen()
            elif c == 't':
                self.on_toggle_tx()
            elif c == 's':
                self.on_snapshot()
            elif c == 'r':
                self.on_reload_cams()
            elif c == 'q':
                self.on_quit()
                break
            else:
                print("Comando desconhecido...")