import os
import tkinter as tk
import tkinter.scrolledtext as st
from tkinter import ttk
import threading
import queue
import time
import ISC_RTT
from PIL import Image, ImageTk
import sys


# import ISC_RTT
# DATOS A TOMAR: DCbus(tensión accu), estado inversor, Torque inversor, pedal accel
os.environ["DISPLAY"] = ":0"

# Queue to hold telemetry data received from NRF24
data_queue = queue.Queue()

# List of available pilots and circuits (you can replace these with actual data)
pilots_list = ["J. Landa", "M. Lorenzo", "A. Montero"]
circuits_list = ["Boadilla", "Jarama", "Montmeló"]

# Flag to control the receiving thread
# receiving_flag = threading.Event()  # Event object to manage the flag

# Function to start receiving data in a background thread

stop_data = 0
# Function to start telemetry based on the selected pilot and circuit


def start_receiving():
    global stop_data
    stop_data = 0
    ISC_RTT.new_data_flag = 0
    piloto = piloto_var.get()  # Get selected pilot
    circuito = circuito_var.get()  # Get selected circuit
    bucket = ISC_RTT.createbucket(piloto, circuito)
    global th
    th = threading.Thread(target=ISC_RTT.receive_data,
                          args=(bucket, piloto, circuito,))
    th.start()
    global th2
    th2 = threading.Thread(target=update_text)
    th2.start()
    # ISC_RTT.receive_data(bucket, piloto, circuito)

# Function to stop telemetry


def stop_receiving():
    piloto = 0
    global stop_data
    stop_data = 1
    ISC_RTT.new_data_flag = -1
    try:
        th2.join()
        th.join()
    except:
        pass


def update_ui():
    try:
        # Continuously check for new data in the queue
        while not data_queue.empty():
            data = data_queue.get()
            telemetry_display.insert(tk.END, data + "\n")
            telemetry_display.see(tk.END)  # Auto-scroll to the latest data

    except queue.Empty:
        pass

    # Schedule the function to run again after 100 milliseconds
    root.after(100, update_ui)


# Tkinter GUI setup
root = tk.Tk()
root.title("ISC RTT")
root.attributes('-fullscreen', True)
root.configure(bg="#101010")

# Grid layout
root.grid_columnconfigure(0, weight=1)
root.grid_columnconfigure(1, weight=1)
root.grid_columnconfigure(2, weight=1)
root.grid_columnconfigure(3, weight=1)
root.grid_columnconfigure(4, weight=1)

# Header Label
logo = Image.open("/home/pi/ISC_REAL_TIME/isc_logo.png")
logo = logo.resize((50, 50), Image.ANTIALIAS)

tk_logo = ImageTk.PhotoImage(logo)
header_label = tk.Label(root, text="ISC RT Telemetry", font=(
    "Inter", 22), fg="#FFFFFF", bg="#101010", image=tk_logo, compound="left", padx=10)
header_label.grid(row=0, column=1, columnspan=2, pady=0)


def exit_program():
    stop_receiving()
    sys.exit(0)


exit_button = tk.Button(root, text="EXIT", font=(
    "Inter", 16), fg="#FFFFFF", bg="#FF0000", command=exit_program)
exit_button.grid(row=0, column=3, pady=10)

# Dropdown menus for pilot and circuit
piloto_var = tk.StringVar(root)
piloto_var.set(pilots_list[0])  # Set default value

circuito_var = tk.StringVar(root)
circuito_var.set(circuits_list[0])  # Set default value

# Pilot Dropdown
pilot_label = tk.Label(root, text="Select Pilot", font=(
    "Inter", 16), fg="#FFFFFF", bg="#101010")
pilot_label.grid(row=1, column=0, padx=5, pady=5)
pilot_menu = tk.OptionMenu(root, piloto_var, *pilots_list)
pilot_menu.config(font=("Inter", 16), fg="#00FF00", bg="#101010")
pilot_menu.grid(row=2, column=0, padx=5, pady=5)

# Circuit Dropdown
circuit_label = tk.Label(root, text="Select Circuit", font=(
    "Inter", 16), fg="#FFFFFF", bg="#101010")
circuit_label.grid(row=1, column=1, padx=5, pady=5)
circuit_menu = tk.OptionMenu(root, circuito_var, *circuits_list)
circuit_menu.config(font=("Inter", 16), fg="#00FF00", bg="#101010")
circuit_menu.grid(row=2, column=1, padx=5, pady=5)

# Buttons
run_button = tk.Button(root, text="RUN", font=(
    "Inter", 16), fg="#FFFFFF", bg="#006400", command=start_receiving)
run_button.grid(row=2, column=2, pady=10)

stop_button = tk.Button(root, text="STOP", font=(
    "Inter", 16), fg="#FFFFFF", bg="#FF0000", command=stop_receiving)
stop_button.grid(row=2, column=3, pady=10)

telemetry_display = st.ScrolledText(width=90, font=("Inter", 14), height=13)
telemetry_display.grid(row=3, column=0, columnspan=4, pady=10, padx=10)
# Exit Fullscreen Mode with 'Escape'


def update_text():

    while stop_data != 1:

        if ISC_RTT.new_data_flag == 1:

            telemetry_display.insert(tk.END, ISC_RTT.data_str + "\n")
            telemetry_display.see("end")
            ISC_RTT.new_data_flag = 0
        time.sleep(0.01)


def close_fullscreen(event):
    root.attributes('-fullscreen', False)


root.bind("<Escape>", close_fullscreen)

# Start the UI update loop
update_ui()

# Run the Tkinter main loop
root.mainloop()
