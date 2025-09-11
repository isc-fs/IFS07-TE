"""
Interfaz Gráfica para Sistema de Telemetría Formula Student
Muestra datos en tiempo real con cuadros informativos y gráficos
"""

import os
import tkinter as tk
import tkinter.scrolledtext as st
from tkinter import ttk, messagebox
import threading
import queue
import time
import ISC_RTT_serial as ISC_RTT
from PIL import Image, ImageTk
import sys, os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np
from collections import deque

if sys.platform.startswith("linux") and "DISPLAY" not in os.environ:
    os.environ["DISPLAY"] = ":0"

class TelemetryUI:
    """Clase principal para la interfaz de telemetría"""
    
    def __init__(self):
        self.setup_data_structures()
        self.setup_ui()
        
        #self.setup_threads()

    def setup_threads(self):
        pass  # Placeholder if needed for future thread setup

    def minimize_window(self):
        """Minimiza la ventana de la aplicación"""
        if self.root.attributes('-fullscreen'):
            self.root.attributes('-fullscreen', False)
        self.root.iconify()

    def close_window(self):
        """Cierra la ventana de la aplicación"""
        self.exit_program()

    
        
    def setup_data_structures(self):
        """Inicializa las estructuras de datos para la telemetría"""
        # Colas para comunicación entre threads
        self.data_queue = queue.Queue()
        
        # Flags de control
        self.receiving_flag = False
        self.stop_data = False
        
        # Threads
        self.receiving_thread = None
        self.ui_update_thread = None
        
        # Datos históricos para gráficos (últimos 100 valores)
        self.throttle_history = deque(maxlen=100)
        self.brake_history = deque(maxlen=100)
        self.time_history = deque(maxlen=100)
        
        # Listas de pilotos y circuitos
        self.pilots_list = ["J. Landa", "M. Lorenzo", "A. Montero", "F. Tobar", "Chefo"]
        self.circuits_list = ["Boadilla", "Jarama", "Montmeló", "Hockenheim"]

    def setup_ui(self):
        """Configura la interfaz de usuario"""
        # Ventana principal
        self.root = tk.Tk()
        self.root.title("ISC Real-Time Telemetry")
        self.root.attributes('-fullscreen', True)
        self.root.configure(bg="#101010")
        
        # Configurar grid principal
        for i in range(6):
            self.root.grid_columnconfigure(i, weight=1)
        for i in range(8):
            self.root.grid_rowconfigure(i, weight=1)
        
        self.create_header()
        self.create_controls()
        self.create_data_displays()
        self.create_graphs()
        self.setup_bindings()

    def create_header(self):
        """Header con logo+título centrado y botones de ventana a la derecha"""
            # --- fila 0: una barra horizontal con 3 zonas (izq, centro, dcha) ---
        # 6 columnas ya configuradas en setup_ui()
        # Zona centro: título con (opcional) logo
        center_frame = tk.Frame(self.root, bg="#101010")
        center_frame.grid(row=0, column=0, columnspan=6, sticky="n", pady=10)

        try:
            from PIL import Image, ImageTk
            logo = Image.open("ISC_REAL_TIME_25/isc_logo.png")
            logo = logo.resize((50, 50), Image.Resampling.LANCZOS)
            self.tk_logo = ImageTk.PhotoImage(logo)
            title = tk.Label(
                center_frame,
                text="ISC Real-Time Telemetry",
                font=("Inter", 22, "bold"),
                fg="#FFFFFF",
                bg="#101010",
                image=self.tk_logo,
                compound="left",
                padx=10,
            )
        except Exception:
            title = tk.Label(
                center_frame,
                text="ISC Real-Time Telemetry",
                font=("Inter", 22, "bold"),
                fg="#FFFFFF",
                bg="#101010",
            )
        title.pack()

        # Zona derecha: botones minimizar y cerrar
        right_frame = tk.Frame(self.root, bg="#101010")
        right_frame.grid(row=0, column=5, sticky="ne", padx=10, pady=10)

        btn_min = tk.Button(
            right_frame, text="—",  # guion largo
            font=("Inter", 14, "bold"),
            fg="#FFFFFF", bg="#303030", activebackground="#505050",
            width=3, borderwidth=0, command=self.minimize_window
        )
        btn_min.pack(side="left", padx=(0, 6))

        btn_close = tk.Button(
            right_frame, text="×",
            font=("Inter", 14, "bold"),
            fg="#FFFFFF", bg="#C43131", activebackground="#E04B4B",
            width=3, borderwidth=0, command=self.close_window
        )
        btn_close.pack(side="left")

        

    def create_controls(self):
        """Selectores centrados bajo el título y botones debajo"""
        # Marco principal centrado para selects
        selects_frame = tk.Frame(self.root, bg="#101010")
        selects_frame.grid(row=1, column=0, columnspan=6, sticky="n", pady=(5, 0))

        # Submarco con grid de 2 columnas (Piloto | Circuito)
        form = tk.Frame(selects_frame, bg="#101010")
        form.pack()

        # Variables
        self.piloto_var = tk.StringVar(self.root, value=self.pilots_list[0])
        self.circuito_var = tk.StringVar(self.root, value=self.circuits_list[0])

        # Piloto
        pilot_label = tk.Label(form, text="Piloto", font=("Inter", 14),
                            fg="#FFFFFF", bg="#101010")
        pilot_label.grid(row=0, column=0, padx=10, pady=(5, 2), sticky="s")
        self.pilot_menu = tk.OptionMenu(form, self.piloto_var, *self.pilots_list)
        self.pilot_menu.config(font=("Inter", 12), fg="#00FF00", bg="#202020",
                            highlightthickness=0, bd=0)
        self.pilot_menu.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Circuito
        circuit_label = tk.Label(form, text="Circuito", font=("Inter", 14),
                                fg="#FFFFFF", bg="#101010")
        circuit_label.grid(row=0, column=1, padx=10, pady=(5, 2), sticky="s")
        self.circuit_menu = tk.OptionMenu(form, self.circuito_var, *self.circuits_list)
        self.circuit_menu.config(font=("Inter", 12), fg="#00FF00", bg="#202020",
                                highlightthickness=0, bd=0)
        self.circuit_menu.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")

        # Marco para botones debajo de los selects
        buttons_frame = tk.Frame(self.root, bg="#101010")
        buttons_frame.grid(row=2, column=0, columnspan=6, sticky="n", pady=(0, 10))

        self.run_button = tk.Button(
            buttons_frame, text="INICIAR",
            font=("Inter", 14, "bold"), fg="#FFFFFF", bg="#006400",
            command=self.start_receiving, relief="raised", bd=2, width=12)
        self.run_button.pack(side="left", padx=8)

        self.stop_button = tk.Button(
            buttons_frame, text="PARAR",
            font=("Inter", 14, "bold"), fg="#FFFFFF", bg="#CC0000",
            command=self.stop_receiving, relief="raised", bd=2, width=12, state="disabled")
        self.stop_button.pack(side="left", padx=8)
    
    def setup_bindings(self):
        self.root.bind("<Escape>", self.close_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Control-m>", lambda e: self.minimize_window())



    def create_data_displays(self):
        """Crea los cuadros de visualización de datos"""
        # Frame para datos del acumulador
        accu_frame = tk.LabelFrame(
            self.root, text="ACUMULADOR", 
            font=("Inter", 12, "bold"),
            fg="#00FF00", bg="#101010", bd=2
        )
        accu_frame.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        
        # Labels para datos del acumulador
        self.accu_voltage_label = tk.Label(
            accu_frame, text="DC Bus: -- V", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.accu_voltage_label.pack(pady=2)
        
        self.accu_current_label = tk.Label(
            accu_frame, text="Corriente: -- A", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.accu_current_label.pack(pady=2)
        
        self.accu_power_label = tk.Label(
            accu_frame, text="Potencia: -- W", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.accu_power_label.pack(pady=2)
        
        # Frame para temperaturas del acumulador
        temp_frame = tk.LabelFrame(
            self.root, text="TEMPERATURAS", 
            font=("Inter", 12, "bold"),
            fg="#FFA500", bg="#101010", bd=2
        )
        temp_frame.grid(row=3, column=2, columnspan=2, padx=5, pady=5, sticky="nsew")
        
        # Labels para temperaturas
        self.temp_accu_label = tk.Label(
            temp_frame, text="Accu Max: -- °C", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.temp_accu_label.pack(pady=2)
        
        self.temp_motor_label = tk.Label(
            temp_frame, text="Motor: -- °C", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.temp_motor_label.pack(pady=2)
        
        self.temp_inverter_label = tk.Label(
            temp_frame, text="Inversor: -- °C", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.temp_inverter_label.pack(pady=2)
        
        # Frame para estado del inversor
        inverter_frame = tk.LabelFrame(
            self.root, text="ESTADO INVERSOR", 
            font=("Inter", 12, "bold"),
            fg="#FF6B6B", bg="#101010", bd=2
        )
        inverter_frame.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")
        
        self.inverter_status_label = tk.Label(
            inverter_frame, text="Estado: DESCONECTADO", 
            font=("Inter", 14, "bold"), fg="#FF0000", bg="#101010"
        )
        self.inverter_status_label.pack(pady=5)
        
        self.inverter_errors_label = tk.Label(
            inverter_frame, text="Errores: --", 
            font=("Inter", 12), fg="#FFFFFF", bg="#101010"
        )
        self.inverter_errors_label.pack(pady=2)
        
        # Frame para torque
        torque_frame = tk.LabelFrame(
            self.root, text="TORQUE", 
            font=("Inter", 12, "bold"),
            fg="#4ECDC4", bg="#101010", bd=2
        )
        torque_frame.grid(row=4, column=2, columnspan=2, padx=5, pady=5, sticky="nsew")
        
        self.torque_req_label = tk.Label(
            torque_frame, text="Solicitado: -- Nm", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.torque_req_label.pack(pady=2)
        
        self.torque_est_label = tk.Label(
            torque_frame, text="Estimado: -- Nm", 
            font=("Inter", 14), fg="#FFFFFF", bg="#101010"
        )
        self.torque_est_label.pack(pady=2)
        
        # Área de log de telemetría
        log_frame = tk.LabelFrame(
            self.root, text="LOG DE TELEMETRÍA", 
            font=("Inter", 12, "bold"),
            fg="#FFFFFF", bg="#101010", bd=2
        )
        log_frame.grid(row=6, column=0, columnspan=6, padx=5, pady=5, sticky="nsew")
        
        self.telemetry_display = st.ScrolledText(
            log_frame, width=100, height=10, 
            font=("Consolas", 10), 
            bg="#1a1a1a", fg="#00FF00"
        )
        self.telemetry_display.pack(fill="both", expand=True, padx=5, pady=5)

    def create_graphs(self):
        """Crea los gráficos de acelerador y freno"""
        # Frame para gráficos
        graphs_frame = tk.Frame(self.root, bg="#101010")
        graphs_frame.grid(row=5, column=0, columnspan=6, padx=5, pady=5, sticky="nsew")
        
        # Configurar matplotlib para tema oscuro
        plt.style.use('dark_background')
        
        # Crear figura para gráficos
        self.fig = Figure(figsize=(12, 4), facecolor='#101010')
        
        # Gráfico de acelerador
        self.ax_throttle = self.fig.add_subplot(121)
        self.ax_throttle.set_title("ACELERADOR (%)", color='white', fontsize=12, fontweight='bold')
        self.ax_throttle.set_ylim(0, 100)
        self.ax_throttle.set_facecolor('#1a1a1a')
        self.ax_throttle.grid(True, alpha=0.3)
        
        # Gráfico de freno
        self.ax_brake = self.fig.add_subplot(122)
        self.ax_brake.set_title("FRENO (%)", color='white', fontsize=12, fontweight='bold')
        self.ax_brake.set_ylim(0, 100)
        self.ax_brake.set_facecolor('#1a1a1a')
        self.ax_brake.grid(True, alpha=0.3)
        
        # Canvas para mostrar gráficos
        self.canvas = FigureCanvasTkAgg(self.fig, master=graphs_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def setup_bindings(self):
        """Configura los eventos de teclado"""
        self.root.bind("<Escape>", self.close_fullscreen)
        self.root.bind("<F11>", self.toggle_fullscreen)

    def start_receiving(self):
        """Inicia la recepción de datos de telemetría"""
        if self.receiving_flag:
            messagebox.showwarning("Aviso", "La recepción ya está en marcha")
            return
        
        try:
            # Resetear flags
            self.stop_data = False
            ISC_RTT.new_data_flag = 0
            self.receiving_flag = True
            
            # Obtener piloto y circuito seleccionados
            piloto = self.piloto_var.get()
            circuito = self.circuito_var.get()
            
            # Crear bucket en InfluxDB
            bucket_id = ISC_RTT.create_bucket(piloto, circuito)
            
            # Iniciar thread de recepción de datos
            self.receiving_thread = threading.Thread(
                target=ISC_RTT.receive_data,
                args=(bucket_id, piloto, circuito),
                daemon=True
            )
            self.receiving_thread.start()
            
            # Iniciar thread de actualización de UI
            self.ui_update_thread = threading.Thread(
                target=self.update_ui_thread,
                daemon=True
            )
            self.ui_update_thread.start()
            
            # Actualizar estado de botones
            self.run_button.config(state="disabled", bg="#404040")
            self.stop_button.config(state="normal", bg="#CC0000")
            
            # Mostrar mensaje en log
            self.log_message(f"Iniciando telemetría: {piloto} en {circuito}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error iniciando recepción: {e}")
            self.receiving_flag = False

    def stop_receiving(self):
        """Para la recepción de datos"""
        if not self.receiving_flag:
            return
        
        try:
            # Establecer flags de parada
            self.stop_data = True
            ISC_RTT.new_data_flag = -1
            self.receiving_flag = False
            
            # Esperar a que terminen los threads
            if self.receiving_thread and self.receiving_thread.is_alive():
                self.receiving_thread.join(timeout=2.0)
            
            if self.ui_update_thread and self.ui_update_thread.is_alive():
                self.ui_update_thread.join(timeout=1.0)
            
            # Actualizar estado de botones
            self.run_button.config(state="normal", bg="#006400")
            self.stop_button.config(state="disabled", bg="#404040")
            
            self.log_message("Recepción de telemetría detenida")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error deteniendo recepción: {e}")

    def update_ui_thread(self):
        """Thread para actualizar la UI con nuevos datos"""
        while not self.stop_data:
            try:
                if ISC_RTT.new_data_flag == 1:
                    # Obtener los últimos datos
                    latest_data = ISC_RTT.get_latest_data()
                    
                    # Programar actualización en el thread principal
                    self.root.after(0, self.update_data_displays, latest_data)
                    self.root.after(0, self.log_message, ISC_RTT.data_str)
                    
                    # Resetear flag
                    ISC_RTT.new_data_flag = 0
                
                time.sleep(0.01)  # 100 Hz de actualización
                
            except Exception as e:
                self.root.after(0, self.log_message, f"Error actualizando UI: {e}")
                break

    def update_data_displays(self, data: dict):
        """Actualiza los displays de datos con la información recibida"""
        try:
            # Actualizar datos del acumulador
            if '0x640' in data:  # ACCUMULATOR
                accu_data = data['0x640']
                if 'current_sensor' in accu_data:
                    self.accu_current_label.config(text=f"Corriente: {accu_data['current_sensor']:.1f} A")
                if 'cell_min_v' in accu_data:
                    self.accu_voltage_label.config(text=f"Voltaje Min: {accu_data['cell_min_v']:.2f} V")
            
            if '0x620' in data:  # POWERTRAIN
                pt_data = data['0x620']
                if 'dc_bus_voltage' in pt_data:
                    self.accu_voltage_label.config(text=f"DC Bus: {pt_data['dc_bus_voltage']:.1f} V")
                if 'dc_bus_power' in pt_data:
                    self.accu_power_label.config(text=f"Potencia: {pt_data['dc_bus_power']:.1f} W")
                if 'motor_temp' in pt_data:
                    self.temp_motor_label.config(text=f"Motor: {pt_data['motor_temp']:.1f} °C")
                if 'pwrstg_temp' in pt_data:
                    self.temp_inverter_label.config(text=f"Inversor: {pt_data['pwrstg_temp']:.1f} °C")
            
            # Actualizar temperaturas del acumulador
            if '0x640' in data:
                accu_data = data['0x640']
                if 'cell_max_temp' in accu_data:
                    temp = accu_data['cell_max_temp']
                    color = "#FF0000" if temp > 50 else "#FFA500" if temp > 40 else "#FFFFFF"
                    self.temp_accu_label.config(text=f"Accu Max: {temp:.1f} °C", fg=color)
            
            # Actualizar estado del inversor
            if '0x680' in data:  # INVERTER_STATUS
                inv_data = data['0x680']
                if 'status' in inv_data:
                    status = int(inv_data['status'])
                    status_text = "CONECTADO" if status == 1 else "DESCONECTADO"
                    status_color = "#00FF00" if status == 1 else "#FF0000"
                    self.inverter_status_label.config(text=f"Estado: {status_text}", fg=status_color)
                
                if 'errors' in inv_data:
                    errors = int(inv_data['errors'])
                    error_color = "#FF0000" if errors > 0 else "#FFFFFF"
                    self.inverter_errors_label.config(text=f"Errores: {errors}", fg=error_color)
            
            # Actualizar torque
            if '0x630' in data:  # DRIVER_INPUTS
                driver_data = data['0x630']
                if 'torque_req' in driver_data:
                    self.torque_req_label.config(text=f"Solicitado: {driver_data['torque_req']:.1f} Nm")
                if 'torque_est' in driver_data:
                    self.torque_est_label.config(text=f"Estimado: {driver_data['torque_est']:.1f} Nm")
                
                # Actualizar gráficos de pedales
                if 'throttle' in driver_data and 'brake' in driver_data:
                    self.update_pedal_graphs(driver_data['throttle'], driver_data['brake'])
            
        except Exception as e:
            self.log_message(f"Error actualizando displays: {e}")

    def update_pedal_graphs(self, throttle: float, brake: float):
        """Actualiza los gráficos de acelerador y freno"""
        try:
            current_time = time.time()
            
            # Añadir nuevos datos a las colas
            self.throttle_history.append(throttle)
            self.brake_history.append(brake)
            self.time_history.append(current_time)
            
            # Limpiar gráficos
            self.ax_throttle.clear()
            self.ax_brake.clear()
            
            # Configurar gráficos
            self.ax_throttle.set_title("ACELERADOR (%)", color='white', fontsize=12, fontweight='bold')
            self.ax_throttle.set_ylim(0, 100)
            self.ax_throttle.set_facecolor('#1a1a1a')
            self.ax_throttle.grid(True, alpha=0.3)
            
            self.ax_brake.set_title("FRENO (%)", color='white', fontsize=12, fontweight='bold')
            self.ax_brake.set_ylim(0, 100)
            self.ax_brake.set_facecolor('#1a1a1a')
            self.ax_brake.grid(True, alpha=0.3)
            
            # Plotear datos si hay suficientes
            if len(self.throttle_history) > 1:
                time_range = np.array(self.time_history) - self.time_history[0]
                
                self.ax_throttle.plot(time_range, self.throttle_history, 'g-', linewidth=2)
                self.ax_throttle.fill_between(time_range, 0, self.throttle_history, alpha=0.3, color='green')
                
                self.ax_brake.plot(time_range, self.brake_history, 'r-', linewidth=2)
                self.ax_brake.fill_between(time_range, 0, self.brake_history, alpha=0.3, color='red')
            
            # Actualizar canvas
            self.canvas.draw()
            
        except Exception as e:
            self.log_message(f"Error actualizando gráficos: {e}")

    def log_message(self, message: str):
        """Añade un mensaje al log de telemetría"""
        try:
            timestamp = time.strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            
            self.telemetry_display.insert(tk.END, formatted_message + "\n")
            self.telemetry_display.see(tk.END)
            
            # Limitar el número de líneas en el log
            lines = self.telemetry_display.get("1.0", tk.END).split('\n')
            if len(lines) > 500:  # Mantener solo las últimas 500 líneas
                self.telemetry_display.delete("1.0", f"{len(lines)-500}.0")
                
        except Exception as e:
            print(f"Error añadiendo mensaje al log: {e}")

    def close_fullscreen(self, event=None):
        """Sale del modo pantalla completa"""
        self.root.attributes('-fullscreen', False)

    def toggle_fullscreen(self, event=None):
        """Alterna el modo pantalla completa"""
        is_fullscreen = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_fullscreen)

    def exit_program(self):
        """Cierra el programa de forma segura"""
        try:
            # Parar recepción si está activa
            if self.receiving_flag:
                self.stop_receiving()
            
            # Cerrar ventana
            self.root.quit()
            self.root.destroy()
            sys.exit(0)
            
        except Exception as e:
            print(f"Error cerrando programa: {e}")
            sys.exit(1)

    def run(self):
        """Inicia la aplicación"""
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.exit_program()

# Punto de entrada principal
if __name__ == "__main__":
    print("=== Iniciando ISC Real-Time Telemetry UI ===")
    
    try:
        app = TelemetryUI()
        app.run()
    except Exception as e:
        print(f"Error fatal en la aplicación: {e}")
        sys.exit(1)
