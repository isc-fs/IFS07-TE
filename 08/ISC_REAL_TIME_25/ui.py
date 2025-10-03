# ui.py
"""
ISCmetrics - Real-Time Telemetry UI
- Fullscreen dark UI
- Select COM port & baudrate
- Optional InfluxDB (Option A backend)
- Excel logging to ./logs via backend
- Debug toggle that streams backend logs into the UI

NOVEDADES UI (robustez):
- Badge LIVE / STALE / TEST / BAD en la cabecera (colores y motivo)
- Si STALE/TEST/BAD: se "congela" la UI (no actualiza números ni gráficas) y se atenúan
- Panel 'ACELERADOR' con Raw1/Raw2, Escalado y Clamped (0..100 %)
"""

import os
import sys
import time
import queue
import threading
import subprocess
import tkinter as tk
import tkinter.scrolledtext as st
from tkinter import ttk, messagebox
import logging

# Backend
import ISC_RTT_serial as ISC_RTT

# ---- Matplotlib in Tk ----
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np
from collections import deque

# Optional logo
try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

# For Linux headless issues
if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"


# -------- Tunables for header logo & spacing --------
LOGO_MAX_HEIGHT = 44   # compact header logo height
LOGO_VPAD_PX    = 6    # transparent vertical padding inside the image
ROW0_PADY       = 2    # header top/bottom padding
ROW1_PADY       = (2, 0)
ROW2_PADY       = (0, 6)
GRAPHS_PADY     = 4
STATUS_PADY     = 0


# -------- path + platform helpers --------
def resource_path(*parts):
    """
    Robust path resolver:
    - Dev mode: relative to this file's directory
    - PyInstaller: uses sys._MEIPASS when present
    - Also tries project subfolder 'ISC_REAL_TIME_25' and CWD as fallbacks
    """
    candidates = []
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(base, *parts))
    except Exception:
        pass
    candidates.append(os.path.join("ISC_REAL_TIME_25", *parts))   # legacy folder
    candidates.append(os.path.join(os.getcwd(), *parts))           # cwd fallback
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


def is_windows():
    return sys.platform.startswith("win")


def load_logo_with_padding(png_path, max_h=LOGO_MAX_HEIGHT, vpad_px=LOGO_VPAD_PX):
    """
    Load PNG, scale by height (preserving aspect), add transparent vertical padding.
    Returns a PIL.Image or None if PIL isn't available.
    """
    if not (Image and ImageTk):
        return None
    img = Image.open(png_path).convert("RGBA")
    w, h = img.size
    if h > max_h:
        new_w = max(1, int(w * (max_h / float(h))))
        try:
            img = img.resize((new_w, max_h), Image.Resampling.LANCZOS)
        except Exception:
            img = img.resize((new_w, max_h), Image.LANCZOS)
    pad_h = img.height + 2 * vpad_px
    padded = Image.new("RGBA", (img.width, pad_h), (0, 0, 0, 0))
    padded.paste(img, (0, vpad_px), img)
    return padded


# -------- logger -> Tk text handler --------
class TkTextHandler(logging.Handler):
    """Send logging records to a Tkinter ScrolledText safely."""
    def __init__(self, text_widget: st.ScrolledText):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        try:
            msg = self.format(record)
            ts = time.strftime("%H:%M:%S")

            def append():
                self.text_widget.insert(tk.END, f"[{ts}] {msg}\n")
                self.text_widget.see(tk.END)
                # trim lines
                lines = self.text_widget.get("1.0", tk.END).split("\n")
                if len(lines) > 600:
                    self.text_widget.delete("1.0", f"{len(lines)-600}.0")

            self.text_widget.after(0, append)
        except Exception:
            self.handleError(record)


class TelemetryUI:
    def __init__(self):
        # Root FIRST
        self.root = tk.Tk()
        self.root.title("ISCmetrics")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="#101010")

        # Early log buffer (avoid using log widget before it exists)
        self._early_logs = []

        # Keep references to images
        self.tk_logo = None

        self.setup_data_structures()
        self.setup_ui()               # builds header, controls, displays (log widget)
        self._flush_early_logs()      # now the log widget exists
        self.setup_logging_bridge()   # route backend logger into UI

    # -------------------- Early logging helpers --------------------
    def _elog(self, message: str):
        """Safe early log: buffer until telemetry_display exists + print to stdout."""
        try:
            print(message)
        except Exception:
            pass
        self._early_logs.append(message)

    def _flush_early_logs(self):
        if hasattr(self, "telemetry_display"):
            for m in self._early_logs:
                self.log_message(m)
            self._early_logs = []

    # -------------------- Infra de estado --------------------
    def setup_data_structures(self):
        self.data_queue = queue.Queue()

        # Flags/threads
        self.receiving_flag = False
        self.stop_data = False
        self.receiving_thread = None
        self.ui_update_thread = None

        # Historias para plots
        self.throttle_history = deque(maxlen=200)
        self.brake_history = deque(maxlen=200)
        self.time_history = deque(maxlen=200)

        # Listas demo
        self.pilots_list = ["J. Landa", "N. Huertas", "A. Sanchez", "F. Tobar"]
        self.circuits_list = ["Boadilla", "Jarama", "Montmeló", "Hockenheim"]

        # Tk variables
        self.selected_port = tk.StringVar(self.root, value="")
        self.selected_baud = tk.IntVar(self.root, value=115200)
        self.use_influx_var = tk.BooleanVar(self.root, value=False)
        self.debug_var = tk.BooleanVar(self.root, value=True)
        self.piloto_var = tk.StringVar(self.root, value=self.pilots_list[0])
        self.circuito_var = tk.StringVar(self.root, value=self.circuits_list[0])
        self.status_var = tk.StringVar(self.root, value="Listo.")

        # Estado de badge
        self.link_badge = tk.StringVar(self.root, value="STALE")
        self.link_reason = tk.StringVar(self.root, value="inicio")

        # Congelar UI cuando STALE/BAD
        self.freeze_ui = True

    # -------------------- UI raíz --------------------
    def setup_ui(self):
        # Grid root
        for i in range(9):
            self.root.grid_columnconfigure(i, weight=1)
        for i in range(8):
            self.root.grid_rowconfigure(i, weight=1)

        self.create_header()
        self.create_controls()
        self.create_data_displays()   # creates self.telemetry_display
        self.create_graphs()
        self.create_statusbar()
        self.setup_bindings()

        # Rellenar combo de puertos al inicio
        self.refresh_ports()

    def setup_bindings(self):
        self.root.bind("<Escape>", self.close_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Control-m>", lambda e: self.minimize_window())

    # -------------------- Cabecera (top-left logo + title) --------------------
    def create_header(self):
        """
        Header layout:
        [ left_group: logo + "ISCmetrics" ] | [ spacer ] | [ right controls ]
        """
        header_bar = tk.Frame(self.root, bg="#101010")
        header_bar.grid(row=0, column=0, columnspan=9, sticky="ew", pady=ROW0_PADY, padx=10)
        header_bar.grid_columnconfigure(0, weight=0)  # left anchored
        header_bar.grid_columnconfigure(1, weight=1)  # spacer
        header_bar.grid_columnconfigure(2, weight=0)  # right controls

        left_group = tk.Frame(header_bar, bg="#101010")
        left_group.grid(row=0, column=0, sticky="nw")

        right_frame = tk.Frame(header_bar, bg="#101010")
        right_frame.grid(row=0, column=2, sticky="ne")

        # ---- Resolve assets
        ico_path = resource_path("isc_logo.ico")
        png_path = resource_path("isc_logo.png")

        # Windows taskbar icon (.ico)
        if is_windows() and os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
                self._elog(f"[ICON] Using ICO for taskbar: {ico_path}")
            except Exception as e:
                self._elog(f"[ICON] iconbitmap failed: {e}")

        # ---- Header logo image (small, aspect preserved, padded)
        self.tk_logo = None
        if os.path.exists(png_path):
            try:
                if Image and ImageTk:
                    pil_img = load_logo_with_padding(png_path, LOGO_MAX_HEIGHT, LOGO_VPAD_PX)
                    if pil_img is None:
                        self.tk_logo = tk.PhotoImage(file=png_path)
                        self._elog(f"[ICON] PNG via Tk PhotoImage (no PIL): {png_path} -> {self.tk_logo.width()}x{self.tk_logo.height()}")
                    else:
                        self.tk_logo = ImageTk.PhotoImage(pil_img)
                        self._elog(f"[ICON] PNG via Pillow (small, padded): {png_path} -> {self.tk_logo.width()}x{self.tk_logo.height()}")
                else:
                    # Fallback without PIL (no resize/padding)
                    self.tk_logo = tk.PhotoImage(file=png_path)
                    self._elog(f"[ICON] PNG via Tk PhotoImage (no PIL): {png_path} -> {self.tk_logo.width()}x{self.tk_logo.height()}")
            except Exception as e:
                self._elog(f"[ICON] Failed to load PNG logo: {png_path} ({e})")
        else:
            self._elog(f"[ICON] PNG not found: {png_path}")

        # Set window iconphoto on all platforms (in addition to iconbitmap on Win)
        if self.tk_logo:
            try:
                self.root.iconphoto(True, self.tk_logo)
            except Exception as e:
                self._elog(f"[ICON] iconphoto failed: {e}")

        # ---- Left: logo + title (tight spacing, top-left anchored)
        if self.tk_logo:
            tk.Label(left_group, image=self.tk_logo, bg="#101010").pack(side="left")
        else:
            tk.Label(left_group, text=" ", bg="#101010").pack(side="left")

        title_lbl = tk.Label(
            left_group,
            text="ISCmetrics",
            font=("Inter", 17, "bold"),
            fg="#FFFFFF",
            bg="#101010",
            padx=8
        )
        title_lbl.pack(side="left")

        # ---- Right side controls (badge + buttons)
        self.badge_label = tk.Label(
            right_frame, textvariable=self.link_badge, font=("Inter", 11, "bold"),
            fg="#000000", bg="#808080", padx=8, pady=3, relief="flat", width=8
        )
        self.badge_label.pack(side="left", padx=(0, 8))

        self.badge_reason_label = tk.Label(
            right_frame, textvariable=self.link_reason, font=("Inter", 9),
            fg="#BBBBBB", bg="#101010", anchor="e", width=24
        )
        self.badge_reason_label.pack(side="left", padx=(0, 8))

        btn_min = tk.Button(
            right_frame, text="—", font=("Inter", 13, "bold"),
            fg="#FFFFFF", bg="#303030", activebackground="#505050",
            width=3, borderwidth=0, command=self.minimize_window
        )
        btn_min.pack(side="left", padx=(0, 6))

        btn_close = tk.Button(
            right_frame, text="×", font=("Inter", 13, "bold"),
            fg="#FFFFFF", bg="#C43131", activebackground="#E04B4B",
            width=3, borderwidth=0, command=self.close_window
        )
        btn_close.pack(side="left")

        # Debug info (buffered until log exists)
        self._elog(f"[ICON] CWD: {os.getcwd()}")
        self._elog(f"[ICON] Resolved ICO: {ico_path} (exists={os.path.exists(ico_path)})")
        self._elog(f"[ICON] Resolved PNG: {png_path} (exists={os.path.exists(png_path)})")

    # -------------------- Controles superiores --------------------
    def create_controls(self):
        # Selects (fila 1) — tighter padding to pull UI up
        selects_frame = tk.Frame(self.root, bg="#101010")
        selects_frame.grid(row=1, column=0, columnspan=9, sticky="n", pady=ROW1_PADY)

        form = tk.Frame(selects_frame, bg="#101010")
        form.pack(anchor="w")

        # Piloto
        tk.Label(form, text="Piloto", font=("Inter", 13), fg="#FFFFFF", bg="#101010").grid(
            row=0, column=0, padx=8, pady=(2, 2), sticky="s"
        )
        self.pilot_menu = tk.OptionMenu(form, self.piloto_var, *self.pilots_list)
        self.pilot_menu.config(font=("Inter", 12), fg="#00FF00", bg="#202020", highlightthickness=0, bd=0)
        self.pilot_menu.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")

        # Circuito
        tk.Label(form, text="Circuito", font=("Inter", 13), fg="#FFFFFF", bg="#101010").grid(
            row=0, column=1, padx=8, pady=(2, 2), sticky="s"
        )
        self.circuit_menu = tk.OptionMenu(form, self.circuito_var, *self.circuits_list)
        self.circuit_menu.config(font=("Inter", 12), fg="#00FF00", bg="#202020", highlightthickness=0, bd=0)
        self.circuit_menu.grid(row=1, column=1, padx=8, pady=(0, 6), sticky="ew")

        # Puerto serie + Baud + Influx + Debug (fila 2)
        io_frame = tk.Frame(self.root, bg="#101010")
        io_frame.grid(row=2, column=0, columnspan=9, sticky="n", pady=ROW2_PADY)

        # Puerto
        tk.Label(io_frame, text="Puerto", font=("Inter", 12), fg="#FFFFFF", bg="#101010").grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        self.port_combo = ttk.Combobox(io_frame, textvariable=self.selected_port, width=24, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=(0, 6), pady=2)

        btn_refresh = tk.Button(
            io_frame, text="Actualizar", font=("Inter", 12),
            fg="#FFFFFF", bg="#303030", activebackground="#505050",
            command=self.refresh_ports
        )
        btn_refresh.grid(row=0, column=2, padx=(0, 12), pady=2)

        # Baud
        tk.Label(io_frame, text="Baud", font=("Inter", 12), fg="#FFFFFF", bg="#101010").grid(
            row=0, column=3, padx=(0, 6), pady=2
        )
        self.baud_entry = tk.Entry(io_frame, textvariable=self.selected_baud, width=10, bg="#202020", fg="#00FF00")
        self.baud_entry.grid(row=0, column=4, padx=(0, 12), pady=2)

        # Influx toggle
        self.influx_chk = tk.Checkbutton(
            io_frame, text="Usar InfluxDB", variable=self.use_influx_var,
            onvalue=True, offvalue=False, font=("Inter", 12),
            fg="#FFFFFF", bg="#101010", activebackground="#101010",
            selectcolor="#202020"
        )
        self.influx_chk.grid(row=0, column=5, padx=(0, 12), pady=2, sticky="w")

        # Debug toggle
        self.debug_chk = tk.Checkbutton(
            io_frame, text="Debug", variable=self.debug_var,
            onvalue=True, offvalue=False, font=("Inter", 12),
            fg="#FFFFFF", bg="#101010", activebackground="#101010",
            selectcolor="#202020", command=self._apply_debug_level
        )
        self.debug_chk.grid(row=0, column=6, padx=(0, 12), pady=2, sticky="w")

        # Botones iniciar / parar
        self.run_button = tk.Button(
            io_frame, text="INICIAR", font=("Inter", 14, "bold"),
            fg="#FFFFFF", bg="#006400", command=self.start_receiving, relief="raised", bd=2, width=12
        )
        self.run_button.grid(row=0, column=7, padx=6)

        self.stop_button = tk.Button(
            io_frame, text="PARAR", font=("Inter", 14, "bold"),
            fg="#FFFFFF", bg="#404040", command=self.stop_receiving,
            relief="raised", bd=2, width=12, state="disabled"
        )
        self.stop_button.grid(row=0, column=8, padx=6)

        # Extra row: open logs (reduced spacing)
        tools_frame = tk.Frame(self.root, bg="#101010")
        tools_frame.grid(row=2, column=0, columnspan=9, sticky="s", pady=(12, 0))
        open_logs_btn = tk.Button(
            tools_frame, text="Abrir carpeta logs", font=("Inter", 11),
            fg="#FFFFFF", bg="#303030", activebackground="#505050",
            command=self.open_logs_folder
        )
        open_logs_btn.pack()

    # -------------------- Cuadros de datos --------------------
    def create_data_displays(self):
        # ACUMULADOR
        accu_frame = tk.LabelFrame(self.root, text="ACUMULADOR",
                                   font=("Inter", 12, "bold"), fg="#00FF00",
                                   bg="#101010", bd=2)
        accu_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=4, sticky="nsew")

        self.accu_voltage_label = tk.Label(accu_frame, text="DC Bus: -- V",
                                           font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.accu_voltage_label.pack(pady=2)

        self.accu_current_label = tk.Label(accu_frame, text="Corriente: -- A",
                                           font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.accu_current_label.pack(pady=2)

        self.accu_power_label = tk.Label(accu_frame, text="Potencia: -- W",
                                         font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.accu_power_label.pack(pady=2)

        # TEMPERATURAS
        temp_frame = tk.LabelFrame(self.root, text="TEMPERATURAS",
                                   font=("Inter", 12, "bold"), fg="#FFA500",
                                   bg="#101010", bd=2)
        temp_frame.grid(row=3, column=2, columnspan=2, padx=5, pady=4, sticky="nsew")

        self.temp_accu_label = tk.Label(temp_frame, text="Accu Max: -- °C",
                                        font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.temp_accu_label.pack(pady=2)

        self.temp_motor_label = tk.Label(temp_frame, text="Motor: -- °C",
                                         font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.temp_motor_label.pack(pady=2)

        self.temp_inverter_label = tk.Label(temp_frame, text="Inversor: -- °C",
                                            font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.temp_inverter_label.pack(pady=2)

        # ESTADO INVERSOR
        inverter_frame = tk.LabelFrame(self.root, text="ESTADO INVERSOR",
                                       font=("Inter", 12, "bold"), fg="#FF6B6B",
                                       bg="#101010", bd=2)
        inverter_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=4, sticky="nsew")

        self.inverter_status_label = tk.Label(inverter_frame, text="Estado: DESCONECTADO",
                                              font=("Inter", 14, "bold"), fg="#FF0000", bg="#101010")
        self.inverter_status_label.pack(pady=5)

        self.inverter_errors_label = tk.Label(inverter_frame, text="Errores: --",
                                              font=("Inter", 12), fg="#FFFFFF", bg="#101010")
        self.inverter_errors_label.pack(pady=2)

        # TORQUE
        torque_frame = tk.LabelFrame(self.root, text="TORQUE",
                                     font=("Inter", 12, "bold"), fg="#4ECDC4",
                                     bg="#101010", bd=2)
        torque_frame.grid(row=4, column=2, columnspan=2, padx=5, pady=4, sticky="nsew")

        self.torque_req_label = tk.Label(torque_frame, text="Solicitado: -- Nm",
                                         font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.torque_req_label.pack(pady=2)

        self.torque_est_label = tk.Label(torque_frame, text="Estimado: -- Nm",
                                         font=("Inter", 14), fg="#FFFFFF", bg="#101010")
        self.torque_est_label.pack(pady=2)

        # ACELERADOR (nuevo: raw/escalado/clamped)
        accel_frame = tk.LabelFrame(self.root, text="ACELERADOR",
                                    font=("Inter", 12, "bold"), fg="#00BFFF",
                                    bg="#101010", bd=2)
        accel_frame.grid(row=4, column=4, columnspan=2, padx=5, pady=4, sticky="nsew")

        self.accel_raw1_label = tk.Label(accel_frame, text="Raw1: --", font=("Inter", 13), fg="#FFFFFF", bg="#101010")
        self.accel_raw1_label.pack(pady=2)
        self.accel_raw2_label = tk.Label(accel_frame, text="Raw2: --", font=("Inter", 13), fg="#FFFFFF", bg="#101010")
        self.accel_raw2_label.pack(pady=2)
        self.accel_scaled_label = tk.Label(accel_frame, text="Escalado: -- %", font=("Inter", 13), fg="#FFFFFF", bg="#101010")
        self.accel_scaled_label.pack(pady=2)
        self.accel_clamped_label = tk.Label(accel_frame, text="Clamped: -- %", font=("Inter", 13, "bold"), fg="#FFFFFF", bg="#101010")
        self.accel_clamped_label.pack(pady=2)

        # LOG
        log_frame = tk.LabelFrame(self.root, text="LOG",
                                  font=("Inter", 12, "bold"), fg="#FFFFFF",
                                  bg="#101010", bd=2)
        log_frame.grid(row=6, column=0, columnspan=9, padx=5, pady=4, sticky="nsew")

        self.telemetry_display = st.ScrolledText(
            log_frame, width=100, height=12, font=("Consolas", 10),
            bg="#1a1a1a", fg="#00FF00"
        )
        self.telemetry_display.pack(fill="both", expand=True, padx=5, pady=5)

    # -------------------- Gráficos --------------------
    def create_graphs(self):
        graphs_frame = tk.Frame(self.root, bg="#101010")
        graphs_frame.grid(row=5, column=0, columnspan=9, padx=5, pady=GRAPHS_PADY, sticky="nsew")

        plt.style.use("dark_background")
        self.fig = Figure(figsize=(12, 4), facecolor="#101010")

        self.ax_throttle = self.fig.add_subplot(121)
        self.ax_throttle.set_title("ACELERADOR (%)", color="white", fontsize=12, fontweight="bold")
        self.ax_throttle.set_ylim(0, 100)
        self.ax_throttle.set_facecolor("#1a1a1a")
        self.ax_throttle.grid(True, alpha=0.3)

        self.ax_brake = self.fig.add_subplot(122)
        self.ax_brake.set_title("FRENO (%)", color="white", fontsize=12, fontweight="bold")
        self.ax_brake.set_ylim(0, 100)
        self.ax_brake.set_facecolor("#1a1a1a")
        self.ax_brake.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.fig, master=graphs_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    # -------------------- Statusbar --------------------
    def create_statusbar(self):
        sb = tk.Frame(self.root, bg="#151515")
        sb.grid(row=7, column=0, columnspan=9, sticky="ew", pady=STATUS_PADY)
        for i in range(9):
            sb.grid_columnconfigure(i, weight=1)

        self.status_label = tk.Label(
            sb, textvariable=self.status_var, anchor="w",
            font=("Inter", 11), fg="#DDDDDD", bg="#151515", padx=8, pady=4
        )
        self.status_label.grid(row=0, column=0, columnspan=9, sticky="ew")

    # -------------------- Logging bridge --------------------
    def setup_logging_bridge(self):
        """Route backend logger into the UI text area."""
        self.tk_log_handler = TkTextHandler(self.telemetry_display)
        formatter = logging.Formatter("%(levelname)s - %(name)s - %(message)s")
        self.tk_log_handler.setFormatter(formatter)

        self.backend_logger = logging.getLogger("ISC_RTT_USB")
        self.backend_logger.addHandler(self.tk_log_handler)
        self._apply_debug_level()

        # Flush anything buffered before the log existed
        self._flush_early_logs()

    def _apply_debug_level(self):
        self.backend_logger.setLevel(logging.DEBUG if self.debug_var.get() else logging.INFO)

    # -------------------- Acciones de ventana --------------------
    def minimize_window(self):
        if self.root.attributes("-fullscreen"):
            self.root.attributes("-fullscreen", False)
        self.root.iconify()

    def close_window(self):
        self.exit_program()

    def close_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", False)

    def toggle_fullscreen(self, event=None):
        self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))

    # -------------------- Puerto serie helpers --------------------
    def refresh_ports(self):
        ports = ISC_RTT.list_serial_ports()
        self.port_combo["values"] = [dev for dev, _ in ports]
        if not self.selected_port.get():
            autodet = self._auto_pick_port_from_list(ports)
            if autodet:
                self.selected_port.set(autodet)
        self.status_var.set(f"Puertos detectados: {', '.join([p[0] for p in ports]) or 'ninguno'}")

    def _auto_pick_port_from_list(self, ports):
        for dev, desc in ports:
            d = (desc or "").upper()
            if "CH340" in d or "USB-SERIAL" in d:
                return dev
        return ports[0][0] if ports else ""

    # -------------------- Iniciar / Parar --------------------
    def start_receiving(self):
        if self.receiving_flag:
            messagebox.showwarning("Aviso", "La recepción ya está en marcha")
            return

        port = self.selected_port.get().strip()
        if not port:
            messagebox.showwarning("Puerto", "Selecciona un puerto COM antes de iniciar.")
            return

        try:
            baud = int(self.selected_baud.get())
        except ValueError:
            messagebox.showerror("Baud", "Baud inválido.")
            return

        use_influx = bool(self.use_influx_var.get())
        debug_mode = bool(self.debug_var.get())

        try:
            # Reset flags
            self.stop_data = False
            ISC_RTT.new_data_flag = 0
            self.receiving_flag = True

            piloto = self.piloto_var.get()
            circuito = self.circuito_var.get()

            bucket_id = ISC_RTT.create_bucket(piloto, circuito, use_influx=use_influx)

            # Thread RX
            self.receiving_thread = threading.Thread(
                target=ISC_RTT.receive_data,
                args=(bucket_id, piloto, circuito, port, baud, use_influx, debug_mode),
                daemon=True
            )
            self.receiving_thread.start()

            # Thread UI updates
            self.ui_update_thread = threading.Thread(target=self.update_ui_thread, daemon=True)
            self.ui_update_thread.start()

            # Botones
            self.run_button.config(state="disabled", bg="#404040")
            self.stop_button.config(state="normal", bg="#CC0000")

            mode = "con Influx" if use_influx else "sin Influx"
            dbg = "DEBUG ON" if debug_mode else "DEBUG OFF"
            msg = f"Iniciando telemetría ({mode}, {dbg}): {piloto} en {circuito} | {port} @ {baud}"
            self.log_message(msg)
            self.status_var.set(msg)

        except Exception as e:
            messagebox.showerror("Error", f"Error iniciando recepción: {e}")
            self.receiving_flag = False

    def stop_receiving(self):
        if not self.receiving_flag:
            return

        try:
            self.stop_data = True
            ISC_RTT.new_data_flag = -1
            self.receiving_flag = False

            if self.receiving_thread and self.ui_update_thread:
                if self.receiving_thread.is_alive():
                    self.receiving_thread.join(timeout=2.0)
                if self.ui_update_thread.is_alive():
                    self.ui_update_thread.join(timeout=1.0)

            self.run_button.config(state="normal", bg="#006400")
            self.stop_button.config(state="disabled", bg="#404040")

            self.log_message("Recepción de telemetría detenida")
            self.status_var.set("Detenido.")
        except Exception as e:
            messagebox.showerror("Error", f"Error deteniendo recepción: {e}")

    # -------------------- Loop de actualización UI --------------------
    def update_ui_thread(self):
        while not self.stop_data:
            try:
                if ISC_RTT.new_data_flag == 1:
                    latest_data = ISC_RTT.get_latest_data()
                    self.root.after(0, self.update_badge_and_freeze, latest_data.get("__STATUS__", {}))
                    if latest_data:
                        self.root.after(0, self.update_data_displays, latest_data)
                    self.root.after(0, self.log_message, ISC_RTT.data_str)
                    ISC_RTT.new_data_flag = 0
                time.sleep(0.01)
            except Exception as e:
                self.root.after(0, self.log_message, f"Error actualizando UI: {e}")
                break

    # -------------------- Badge + congelación --------------------
    def update_badge_and_freeze(self, status_obj: dict):
        badge = str(status_obj.get("badge", "STALE")).upper()
        reason = str(status_obj.get("reason", ""))
        self.link_badge.set(badge)
        self.link_reason.set(reason)

        color_map = {
            "LIVE": "#00FF00",
            "STALE": "#BFBF00",
            "TEST": "#FF8C00",
            "BAD": "#FF3333",
        }
        bg = color_map.get(badge, "#808080")
        self.badge_label.config(bg=bg, fg="#000000")

        self.freeze_ui = (badge in {"STALE", "BAD"})
        self._set_widgets_dim(self.freeze_ui)

    def _set_widgets_dim(self, dim: bool):
        fg_dim = "#888888"
        fg_norm = "#FFFFFF"

        labels = [
            self.accu_voltage_label, self.accu_current_label, self.accu_power_label,
            self.temp_accu_label, self.temp_motor_label, self.temp_inverter_label,
            self.inverter_status_label, self.inverter_errors_label,
            self.torque_req_label, self.torque_est_label,
            self.accel_raw1_label, self.accel_raw2_label,
            self.accel_scaled_label, self.accel_clamped_label,
        ]
        for lb in labels:
            try:
                lb.config(fg=fg_dim if dim else fg_norm)
            except Exception:
                pass

        tcolor = fg_dim if dim else "#FFFFFF"
        try:
            self.ax_throttle.set_title("ACELERADOR (%)", color=tcolor, fontsize=12, fontweight="bold")
            self.ax_brake.set_title("FRENO (%)", color=tcolor, fontsize=12, fontweight="bold")
            self.canvas.draw()
        except Exception:
            pass

    # -------------------- Render de datos --------------------
    def update_data_displays(self, data: dict):
        if self.freeze_ui:
            return
        try:
            # ACCUMULATOR (0x640)
            if "0x640" in data:
                accu = data["0x640"]
                if "current_sensor" in accu:
                    self.accu_current_label.config(text=f"Corriente: {accu['current_sensor']:.1f} A")
                if "cell_min_v" in accu:
                    self.accu_voltage_label.config(text=f"Voltaje Min: {accu['cell_min_v']:.2f} V")
                if "cell_max_temp" in accu:
                    temp = float(accu["cell_max_temp"])
                    color = "#FF0000" if temp > 50 else "#FFA500" if temp > 40 else "#FFFFFF"
                    self.temp_accu_label.config(text=f"Accu Max: {temp:.1f} °C", fg=color if not self.freeze_ui else "#888888")

            # POWERTRAIN (0x620)
            if "0x620" in data:
                pt = data["0x620"]
                if "dc_bus_voltage" in pt:
                    self.accu_voltage_label.config(text=f"DC Bus: {pt['dc_bus_voltage']:.1f} V")
                if "dc_bus_power" in pt:
                    self.accu_power_label.config(text=f"Potencia: {pt['dc_bus_power']:.1f} W")
                if "motor_temp" in pt:
                    self.temp_motor_label.config(text=f"Motor: {pt['motor_temp']:.1f} °C")
                if "pwrstg_temp" in pt:
                    self.temp_inverter_label.config(text=f"Inversor: {pt['pwrstg_temp']:.1f} °C")

            # INVERTER STATUS (0x680)
            if "0x680" in data:
                inv = data["0x680"]
                if "status" in inv:
                    status = int(inv["status"])
                    status_text = "CONECTADO" if status == 1 else "DESCONECTADO"
                    status_color = "#00FF00" if status == 1 else "#FF0000"
                    self.inverter_status_label.config(text=f"Estado: {status_text}",
                                                      fg=status_color if not self.freeze_ui else "#888888")
                if "errors" in inv:
                    errors = int(inv["errors"])
                    error_color = "#FF0000" if errors > 0 else "#FFFFFF"
                    self.inverter_errors_label.config(text=f"Errores: {errors}",
                                                      fg=error_color if not self.freeze_ui else "#888888")

            # DRIVER INPUTS (0x630)
            if "0x630" in data:
                drv = data["0x630"]
                if "torque_req" in drv:
                    self.torque_req_label.config(text=f"Solicitado: {drv['torque_req']:.1f} Nm")
                if "torque_est" in drv:
                    self.torque_est_label.config(text=f"Estimado: {drv['torque_est']:.1f} Nm")
                throttle = None
                brake = None
                if "throttle" in drv:
                    throttle = float(drv["throttle"])
                if "brake" in drv:
                    brake = float(drv["brake"])
                if throttle is not None and brake is not None:
                    self.update_pedal_graphs(throttle, brake)

            # ACELERADOR – raw/escalado/clamped (fuente 0x600 y 0x630)
            raw1 = raw2 = None
            scaled = None
            if "0x600" in data:
                m600 = data["0x600"]
                raw1 = m600.get("throttle_raw1", None)
                raw2 = m600.get("throttle_raw2", None)
            if "0x630" in data:
                m630 = data["0x630"]
                scaled = m630.get("throttle", None)

            if raw1 is not None:
                self.accel_raw1_label.config(text=f"Raw1: {raw1:.2f}")
            if raw2 is not None:
                self.accel_raw2_label.config(text=f"Raw2: {raw2:.2f}")
            if scaled is not None:
                clamped = max(0.0, min(100.0, float(scaled)))
                self.accel_scaled_label.config(text=f"Escalado: {scaled:.2f} %")
                self.accel_clamped_label.config(text=f"Clamped:  {clamped:.2f} %")

        except Exception as e:
            self.log_message(f"Error actualizando displays: {e}")

    # -------------------- Gráficas pedales --------------------
    def update_pedal_graphs(self, throttle: float, brake: float):
        if self.freeze_ui:
            return
        try:
            t_now = time.time()
            self.throttle_history.append(float(throttle))
            self.brake_history.append(float(brake))
            self.time_history.append(t_now)

            self.ax_throttle.clear()
            self.ax_brake.clear()

            self.ax_throttle.set_title("ACELERADOR (%)", color="white", fontsize=12, fontweight="bold")
            self.ax_throttle.set_ylim(0, 100)
            self.ax_throttle.set_facecolor("#1a1a1a")
            self.ax_throttle.grid(True, alpha=0.3)

            self.ax_brake.set_title("FRENO (%)", color="white", fontsize=12, fontweight="bold")
            self.ax_brake.set_ylim(0, 100)
            self.ax_brake.set_facecolor("#1a1a1a")
            self.ax_brake.grid(True, alpha=0.3)

            if len(self.throttle_history) > 1:
                t0 = self.time_history[0]
                ts = np.array(self.time_history) - t0
                self.ax_throttle.plot(ts, self.throttle_history, "g-", linewidth=2)
                self.ax_throttle.fill_between(ts, 0, self.throttle_history, alpha=0.3, color="green")
                self.ax_brake.plot(ts, self.brake_history, "r-", linewidth=2)
                self.ax_brake.fill_between(ts, 0, self.brake_history, alpha=0.3, color="red")

            self.canvas.draw()
        except Exception as e:
            self.log_message(f"Error actualizando gráficos: {e}")

    # -------------------- Utilities --------------------
    def open_logs_folder(self):
        path = os.path.abspath("logs")
        os.makedirs(path, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Abrir carpeta", f"No se pudo abrir la carpeta de logs:\n{e}")

    # -------------------- Log y salida --------------------
    def log_message(self, message: str):
        try:
            ts = time.strftime("%H:%M:%S")
            self.telemetry_display.insert(tk.END, f"[{ts}] {message}\n")
            self.telemetry_display.see(tk.END)
            # Limitar a 600 líneas
            lines = self.telemetry_display.get("1.0", tk.END).split("\n")
            if len(lines) > 600:
                self.telemetry_display.delete("1.0", f"{len(lines)-600}.0")
        except Exception as e:
            print(f"Error añadiendo mensaje al log: {e}")

    def exit_program(self):
        try:
            if self.receiving_flag:
                self.stop_receiving()
            self.root.quit()
            self.root.destroy()
            sys.exit(0)
        except Exception as e:
            print(f"Error cerrando programa: {e}")
            sys.exit(1)

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.exit_program()


# -------------------- Main --------------------
if __name__ == "__main__":
    print("=== Iniciando ISCmetrics UI ===")
    try:
        app = TelemetryUI()
        app.run()
    except Exception as e:
        print(f"Error fatal en la aplicación: {e}")
        sys.exit(1)
