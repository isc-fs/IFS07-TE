"""
Recepción por USB-Serial desde RF-NANO (forward de NRF24L01, 32B de 8 floats LE)
Mantiene API esperada por tu UI: new_data_flag, data_str, latest_data_dict,
create_bucket(...), receive_data(bucket_id, piloto, circuito), get_latest_data(...)
"""

import serial
import serial.tools.list_ports
import struct
import time
import logging
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ===== Reusa tu config de Influx =====
INFLUX_CONFIG = {
    "url": "http://localhost:8086",
    "token": "TU_TOKEN",
    "org": "TU_ORG"
}
client = InfluxDBClient(**INFLUX_CONFIG)

# ===== Estados esperados por la UI =====
data_str = ""
new_data_flag = 0
latest_data_dict = {}

logger = logging.getLogger("ISC_RTT_USB")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ===== Protocolo serie (frame) =====
SOF1 = 0xAA
SOF2 = 0x55
PAYLOAD_LEN = 32

# ======= Tuning puerto serie por defecto =======
DEFAULT_BAUD = 115200
DEFAULT_PORT = None  # Si None, intenta detectar; si no, pon "COM5" o "/dev/ttyUSB0"

# ====== Copia de tu parse_telemetry_data(...) tal cual (recortada aquí) ======
# Pega aquí la función 'parse_telemetry_data(values)' que ya tienes,
# sin cambios, para mantener formato, data_str y latest_data_dict.

def parse_telemetry_data(values):
    # ... Pega tu función original completa aquí ...
    pass

def write_session_metadata(write_api, bucket_id, piloto, circuito):
    # ... Pega tu función original aquí ...
    pass

def create_bucket(piloto: str, circuito: str) -> str:
    # ... Pega tu función original aquí ...
    pass

def get_latest_data(data_id: str = None):
    if data_id:
        return latest_data_dict.get(data_id, {})
    return latest_data_dict.copy()

def _auto_detect_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        # Heurística: CH340 (RF-NANO usa CH340 USB-Serie en muchas variantes)
        if "CH340" in p.description or "USB-SERIAL" in p.description.upper() or "USB-SERIAL CH340" in p.hwid:
            return p.device
    return ports[0].device if ports else None

def _open_serial(port, baud):
    ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
    # DTR reset: algunos Nanos reinician al abrir puerto; espera
    time.sleep(1.5)
    ser.reset_input_buffer()
    return ser

def _read_frame(ser):
    """Bloquea hasta leer un frame válido; devuelve bytes payload de 32B o None."""
    # Buscar SOF
    while True:
        b = ser.read(1)
        if not b:
            return None
        if b[0] == SOF1:
            b2 = ser.read(1)
            if not b2:
                return None
            if b2[0] == SOF2:
                break
    # Longitud
    ln = ser.read(1)
    if not ln or ln[0] != PAYLOAD_LEN:
        return None
    # Payload + checksum
    payload = ser.read(PAYLOAD_LEN)
    if len(payload) != PAYLOAD_LEN:
        return None
    chk = ser.read(1)
    if not chk:
        return None
    # Verificar XOR
    c = 0
    for bb in payload:
        c ^= bb
    if c != chk[0]:
        return None
    return payload

def receive_data(bucket_id: str, piloto: str, circuito: str, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD):
    global new_data_flag, data_str
    logger.info("Recepción USB-Serial iniciada")

    write_api = client.write_api(write_options=SYNCHRONOUS)
    write_session_metadata(write_api, bucket_id, piloto, circuito)

    if port is None:
        port = _auto_detect_port()
    if port is None:
        raise RuntimeError("No se encontró un puerto serie RF-NANO.")

    ser = _open_serial(port, baud)
    logger.info(f"Leyendo de {port} @ {baud} bps")

    try:
        while new_data_flag != -1:
            frame = _read_frame(ser)
            if frame is None:
                continue
            try:
                values = struct.unpack("<ffffffff", frame)
            except struct.error:
                continue

            pt = parse_telemetry_data(values)
            if pt:
                pt = pt.tag("piloto", piloto).tag("circuito", circuito)
                write_api.write(bucket=bucket_id, record=pt)
                new_data_flag = 1  # para que la UI actualice
    finally:
        try:
            ser.close()
        except:
            pass
        logger.info("Recepción USB-Serial finalizada.")
