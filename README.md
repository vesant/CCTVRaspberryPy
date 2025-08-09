# CCTV 2×2 – Windows & Raspberry Pi (até 4 câmaras USB)

Sistema simples de **CCTV** para mostrar até **4 webcams USB** numa grelha 2×2 (ecrã cheio), com envio opcional dos frames para um **servidor TCP**.
Funciona em **Windows** (para desenvolver/testar) e em **Linux/Raspberry Pi OS** (para correr no Raspberry Pi).

---

## ✨ O que já vem pronto

* **Grelha 2×2** em ecrã cheio (ALT+TAB continua a funcionar).
* **Até 4 câmaras USB** (se faltar alguma, o quadrado fica preto).
* **Anti-flicker**: cada câmara mantém sempre o último frame válido (sem “piscar”).
* **Backends por câmara** (Windows: `dshow`/`msmf`; Linux: `v4l2`) para evitar câmaras “sobrepostas”.
* **Forçar MJPG** no Windows (costuma estabilizar webcams USB).
* **Envio para servidor** (opcional) via TCP com protocolo simples (JPEG + cabeçalho + CRC32).
* **Submenu de consola** com comandos rápidos (fullscreen, snapshot, reiniciar câmaras, ligar/desligar envio).
* **Script automático** (`auto_run.py`) que deteta as câmaras e arranca tudo sozinho.

---

## 🗂️ Estrutura do projeto

```
.
├─ main.py                     # Janela (UI), grelha 2×2, integra tudo
├─ auto_run.py                 # Script que deteta câmaras e arranca o main automaticamente
├─ camera_handler/
│  └─ video_audio.py           # Captura por câmara, anti-flicker, grelha
├─ core/
│  └─ dataTX.py                # Envio TCP (JPEG + cabeçalho + CRC32)
├─ options_sub/
│  ├─ subMain.py               # Submenu de consola (thread)
│  └─ tools/
│     └─ tools.py              # save_snapshot
```

---

## 🔧 Requisitos

* **Python 3.8+**
* **Windows**: `pip install opencv-python numpy`
  (PyAudio é opcional; só precisas se fores mesmo gravar áudio)
* **Raspberry Pi OS / Ubuntu**:

  ```bash
  sudo apt-get update
  sudo apt-get install -y python3-opencv python3-numpy
  ```

  (em ARM é melhor usar os pacotes do sistema para evitar builds lentas)

---

## 🚀 Arranque rápido (recomendado)

### 1) Liga as câmaras **antes** de correr

Ligações USB feitas? Boa. Segue.

### 2) Usa o arranque automático

Este script deteta as câmaras, escolhe backends por SO e lança o `main.py` com tudo preparado.

```bash
# Windows ou Linux
python auto_run.py --debug
```

O que ele faz:

* Testa índices (0..8) e seleciona até **4 câmaras** que realmente dão imagem.
* No **Windows** tenta `dshow` primeiro (e ativa `--force-mjpg`).
* No **Linux** usa `v4l2`.
* Depois arranca o `main.py` com `--cams`, `--devs`, `--backends`, `--force-mjpg`, resolução e FPS.

> Queres já enviar para o servidor?

```bash
python auto_run.py --server 192.168.x.x --port 5050 --quality 70 --debug
```

---

## 🎛️ Controlos (teclado e consola)

* Na janela:
  `f` = fullscreen on/off · `t` = ligar/desligar envio (TCP TX) · `s` = guardar snapshot · `q` = sair
* Na **consola** (submenu abre automaticamente):
  `F`/`T`/`S`/`R`/`Q` com as mesmas funções + **R** recarrega câmaras.

Snapshots ficam gravados como `cctv_grid_YYYYMMDD-HHMMSS.jpg` na pasta de execução.

---

## ⚙️ Arranque manual (para quem quer controlar tudo)

Se preferires chamar o `main.py` diretamente (sem auto-detecção):

```bash
# Exemplo típico no Windows: portátil + 1 USB
python main.py --cams 2 --devs 1,0 --backends dshow,msmf --force-mjpg --width 640 --height 360 --fps 15 --debug

# Exemplo típico no Raspberry/Linux:
python3 main.py --cams 2 --devs 0,1 --backends v4l2,v4l2 --width 640 --height 360 --fps 10
```

### Parâmetros importantes

* `--cams N` → quantas câmaras queres (1–4).
* `--devs 0,1,2,...` → **quais índices** abrir (evita abrir “índices fantasmas”).
* `--backends dshow,msmf,v4l2,auto` → **um por slot** (ordem deve bater com `--devs`).
* `--force-mjpg` (Windows) → tenta estabilizar webcams USB.
* Resolução/FPS por câmara: `--width --height --fps`.

> Dica: no Windows, mistura `dshow` e `msmf` entre as duas câmaras.
> Ex.: `--backends dshow,msmf` costuma impedir a “câmara duplicada”.

---

## 📡 Envio para servidor (opcional) (ainda a trabalhar num cliente)

Ativa o envio com `t` durante a execução, ou arranca já com o servidor definido:

```bash
# com o auto_run
python auto_run.py --server 192.168.x.x --port 5050 --quality 70

# ou com o main
python main.py --server 192.168.x.x --port 5050 --quality 70
```

### Protocolo (camada de aplicação)

Cada frame segue este formato:

```
MAGIC(8)=EVOLCCTV |
VER(1) |
CAM(1) |              # 0..3
TS(8, double BE) |    # timestamp do envio
SIZE(4, uint32 BE) |  # bytes do JPEG
JPEG (SIZE bytes) |
CRC32(4, BE)          # do JPEG
```

No servidor, basta:

1. ler o cabeçalho,
2. ler os `SIZE` bytes do JPEG,
3. confirmar o CRC32,
4. decodificar o JPEG (se precisares).

---

## 🧪 Dicas de performance (especialmente no Pi 2)

* Usa **640×360 @ 10–15 fps** (já é fluido e leve).
* Evita áudio no Raspberry (está **desligado** por omissão no código base — ativa só se precisares mesmo).
* Não abras mais que **duas câmaras** no Pi 2 se notares que o CPU vai ao máximo.
* Se estiver “pesado”, baixa `--fps` ou `--width/--height`.

---

## 🩺 Solução de problemas

**Aparece a mesma imagem repetida (C0= C2)?**
→ Estás a abrir índices a mais. Usa **só** os que queres: `--cams 2 --devs 1,0` (e não deixes o programa inventar 2 e 3).
O nosso `MultiCamManager` **não** preenche índices extra quando passas `--devs`.

**Flicker/“a piscar” ou tiles a preto a saltar?**
→ Já mitigado com **anti-flicker** (mantém último frame).
Se ainda acontecer no Windows, usa `--force-mjpg` e combina `--backends dshow,msmf`.

**A câmara USB não abre no Windows?**
→ Tenta trocar backends: `--backends msmf,dshow` (troca a ordem).
→ Reduz para 320×240 só para “agarrar” a câmara e depois volta a 640×360.
→ Troca a porta USB.

**No Linux dá “Permission denied”**
→ Confirma que o teu utilizador está em grupos como `video` (e que `/dev/video*` existe).

**Não envia para o servidor**
→ Confirma firewall (`ufw allow 5050/tcp`), IP, e se o servidor está a escutar.
→ Vê a consola: quando ligas (`t`), aparece “Transmissão: **LIGADA**”.

---

## 🧱 Como funciona por dentro (resumo técnico)

* `camera_handler/video_audio.py`

  * `CameraStream`: 1 thread por câmara, **guarda o último frame** (anti-flicker).
  * `MultiCamManager`: aceita `device_indices` e `backends` por slot; **não** preenche índices extra se passares `--devs`.
  * `make_grid_2x2`: compõe a grelha (tiles pretos quando não há feed).

* `core/dataTX.py`

  * `DataTX`: fila de envio, reconexão automática, `cv2.imencode(.jpg)` com qualidade configurável.

* `main.py`

  * cria janela fullscreen, chama o submenu em **thread** separada, faz snapshots, liga/desliga o envio.

* `auto_run.py`

  * tenta abrir índices 0..N (com backends adequados por SO), escolhe só os que funcionam e arranca o `main.py`.

---

## 🧰 Exemplos de arranque (copy/paste)

**Windows** (portátil + USB, estável):

```bash
python main.py --cams 2 --devs 1,0 --backends dshow,msmf --force-mjpg --width 640 --height 360 --fps 15 --debug
```

**Linux/Raspberry** (duas câmaras):

```bash
python3 main.py --cams 2 --devs 0,1 --backends v4l2,v4l2 --width 640 --height 360 --fps 10
```

**Automático (deteta tudo)**:

```bash
python auto_run.py --debug
```

**Com servidor (na mesma rede)**:

```bash
ainda a desenvolver...
```

---

## 🔐 Notas de segurança

* Este projeto **não** cifra o vídeo; é plain TCP no LAN.
* Para produção, recomenda-se colocar o servidor **atrás de um VPN** ou usar um túnel seguro (ex.: WireGuard), ou então implementar TLS na camada de transporte.

---

## 📜 Licença

Usa à vontade para fins pessoais/educativos. Se fores usar comercialmente, revê as tuas dependências (OpenCV/Numpy) e adapta as partes de rede conforme a tua política.

---

## ❓Precisas de ajuda?

* Abre uma **Issue** com:

  * SO (Windows/Linux),
  * modelos das câmaras,
  * comando usado,
  * print do output do `auto_run.py` (deteção),
  * e, se possível, um pequeno vídeo do comportamento.

made with love by portugueses!
