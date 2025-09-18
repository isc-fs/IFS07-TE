import tkinter as tk
from tkinter import ttk
import threading
import queue
import os

#from ISC_RTT import receive_data, createbucket  # Assuming the telemetry script is named ISC_RTT.py
os.environ["DISPLAY"] = ":0"
# Queue to hold telemetry data received from NRF24
data_queue = queue.Queue()

# List of available pilots and circuits (you can replace these with actual data)
pilots_list = ["J. Landa", "M. Lorenzo", "A. Montero"]
circuits_list = ["Boadilla", "Jarama", "Montmeló"]

# Function to start receiving data in a background thread
def start_receiving(bucketnever, piloto, circuito):
    receiving_thread = threading.Thread(target=receive_data, args=(bucketnever, piloto, circuito, data_queue))
    receiving_thread.daemon = True  # Daemon thread exits when the main program exits
    receiving_thread.start()

# Function to start telemetry based on the selected pilot and circuit
def on_start_button_click():
    piloto = piloto_var.get()  # Get selected pilot
    circuito = circuito_var.get()  # Get selected circuit
    
    bucketnever = createbucket(piloto, circuito)  # Create bucket
    bucket = "296f7f6218c651a2"  # Use fixed bucket ID

    # Start receiving telemetry data
    start_receiving(bucketnever, piloto, circuito)

# Tkinter function to update the UI with received data
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
root.title("ISC Real-Time Telemetry Receiver")
root.geometry("800x600")
root.configure(bg="#101010")

# Header Label
header_label = tk.Label(root, text="ISC Real-Time Telemetry Receiver", font=("OCR A Extended", 24), fg="#FFFFFF", bg="#101010")
header_label.pack(pady=10)

# Dropdown menus for pilot and circuit
piloto_var = tk.StringVar(root)
piloto_var.set(pilots_list[0])  # Set default value

circuito_var = tk.StringVar(root)
circuito_var.set(circuits_list[0])  # Set default value

# Pilot Dropdown
pilot_label = tk.Label(root, text="Select Pilot", font=("OCR A Extended", 16), fg="#FFFFFF", bg="#101010")
pilot_label.pack(pady=5)
pilot_menu = tk.OptionMenu(root, piloto_var, *pilots_list)
pilot_menu.config(font=("OCR A Extended", 16), fg="#00FF00", bg="#101010")
pilot_menu.pack(pady=5)

# Circuit Dropdown
circuit_label = tk.Label(root, text="Select Circuit", font=("OCR A Extended", 16), fg="#FFFFFF", bg="#101010")
circuit_label.pack(pady=5)
circuit_menu = tk.OptionMenu(root, circuito_var, *circuits_list)
circuit_menu.config(font=("OCR A Extended", 16), fg="#00FF00", bg="#101010")
circuit_menu.pack(pady=5)

# Telemetry Display (Text Widget)
telemetry_display = tk.Text(root, height=20, width=80, bg="#151515", fg="#00ff00", font=("Courier", 14))
telemetry_display.pack(padx=10, pady=10)

# Start Telemetry Button
start_button = tk.Button(root, text="Start Telemetry", command=on_start_button_click, font=("OCR A Extended", 16), fg="#FFFFFF", bg="#101010")
start_button.pack(pady=10)

# Exit Fullscreen Mode with 'Escape'
def close_fullscreen(event):
    root.attributes('-fullscreen', False)

root.bind("<Escape>", close_fullscreen)

# Start the UI update loop
update_ui()

# Run the Tkinter main loop
root.mainloop()