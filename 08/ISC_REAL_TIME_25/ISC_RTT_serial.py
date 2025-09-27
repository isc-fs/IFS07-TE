# ISC_RTT_serial.py
"""
Recepción por USB-Serial desde RF-NANO (forward de NRF24L01, 32B LE)
Mantiene API esperada por tu UI:
  - new_data_flag, data_str, latest_data_dict
  - create_bucket(piloto, circuito, use_influx=False) -> bucket_id
  - receive_data(bucket_id, piloto, circuito, port=None, baud=115200, use_influx=False, debug=False)
  - get_latest_data(data_id=None)
  - list_serial_ports()

Además:
  - Log a Excel en carpeta ./logs por sesión (una fila por frame)
  - Decodifica payload nuevo (TelFrame: <HHfffffff>, 32B) y legacy (8 floats)
  - Imprime mensajes estilo Arduino: [CONFIG] y "Radio Checking" periódicos
"""

import os
import time
import struct
import logging
from datetime import datetime

import serial
import serial.tools.list_ports

# Excel logging
import pandas as pd

# ================== CONFIG RF (esperada, para debug/log) ==================
RF_EXPECTED = {
    "PIPE_ADDR": "0xE7E7E7E7E7",
    "CHANNEL":   76,          # 0x4C
    "PAYLOAD":   32,          # bytes
    "DATA_RATE": "1Mbps",
    "AUTO_ACK":  False,       # NO-ACK
    "CRC":       "CRC_16",
    "PA":        "PA_MAX",
}

# ================== CONFIG Influx (OPCIONAL) ==================
INFLUX_CONFIG = {
    "url":   "http://localhost:8086",
    "token": "TU_TOKEN",
    "org":   "TU_ORG",
}
INFLUX_ENABLE_DEFAULT = False   # <-- por defecto DESACTIVADO

_client = None          # se crea perezosamente
_influx_ok = False

def _init_influx():
    """Inicializa el cliente de Influx de forma perezosa."""
    global _client, _influx_ok
    if _client is not None:  # ya intentado
        return
    try:
        from influxdb_client import InfluxDBClient  # import dentro para no fallar si lib no está
        _client = InfluxDBClient(**INFLUX_CONFIG)
        # No prueba conexión todavía; se considera OK hasta que un write falle
        _influx_ok = True
        logging.getLogger("ISC_RTT_USB").info("InfluxDB inicializado: %s", INFLUX_CONFIG["url"])
    except Exception as e:
        _client = None
        _influx_ok = False
        logging.getLogger("ISC_RTT_USB").warning("Influx deshabilitado: %s", e)

def _get_write_api():
    if not _influx_ok or _client is None:
        return None
    try:
        from influxdb_client.client.write_api import SYNCHRONOUS
        return _client.write_api(write_options=SYNCHRONOUS)
    except Exception as e:
        logging.getLogger("ISC_RTT_USB").warning("No se pudo crear write_api: %s", e)
        return None

# ================== MARCO SERIAL ==================
SOF1 = 0xAA
SOF2 = 0x55
PAYLOAD_LEN = 32

DEFAULT_BAUD = 115200
DEFAULT_PORT = None  # autodetect si None

# ================== ESTADO PARA LA UI ==================
data_str = ""
new_data_flag = 0
latest_data_dict = {}

logger = logging.getLogger("ISC_RTT_USB")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ================== UTILIDADES ==================
def _dump_hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)

def list_serial_ports():
    """Devuelve lista de (device, description) para poblar combo de la UI."""
    out = []
    for p in serial.tools.list_ports.comports():
        out.append((p.device, p.description))
    return out

def _auto_detect_port():
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        desc = (p.description or "").upper()
        hwid = (p.hwid or "").upper()
        if "CH340" in desc or "USB-SERIAL" in desc or "CH340" in hwid:
            return p.device
    return ports[0].device if ports else None

def _open_serial(port, baud):
    ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
    # Muchos Nanos reinician al abrir DTR → espera un poco
    time.sleep(1.5)
    ser.reset_input_buffer()
    return ser

def _read_frame(ser, counters=None):
    """
    Frame: SOF1(0xAA) SOF2(0x55) LEN(32) PAYLOAD(32B) XOR(payload)
    Devuelve (payload, err) donde:
      - payload: bytes (32) o None
      - err: None | 'timeout' | 'len' | 'short' | 'chk'
    """
    # Buscar AA 55
    b = ser.read(1)
    if not b:
        if counters is not None: counters["timeout"] += 1
        return None, "timeout"
    if b[0] != SOF1:
        # seguimos escaneando sin contar como error
        return None, None
    b2 = ser.read(1)
    if not b2:
        if counters is not None: counters["timeout"] += 1
        return None, "timeout"
    if b2[0] != SOF2:
        return None, None

    ln = ser.read(1)
    if not ln or ln[0] != PAYLOAD_LEN:
        if counters is not None: counters["len"] += 1
        return None, "len"

    payload = ser.read(PAYLOAD_LEN)
    if len(payload) != PAYLOAD_LEN:
        if counters is not None: counters["short"] += 1
        return None, "short"

    chk = ser.read(1)
    if not chk:
        if counters is not None: counters["timeout"] += 1
        return None, "timeout"

    c = 0
    for bb in payload:
        c ^= bb
    if c != chk[0]:
        if counters is not None: counters["chk"] += 1
        return None, "chk"

    return payload, None

# ================== DECODIFICACIÓN PAYLOAD ==================
def _decode_payload(payload: bytes):
    """
    Intenta decodificar como TelFrame (2x uint16 + 7 floats).
    Si falla, intenta legacy (8 floats).
    Devuelve dict con: id, seq (o None), v1..v7, raw_floats, fmt
    """
    assert len(payload) == 32

    # Nuevo: TelFrame
    try:
        id_u16, seq_u16, v1, v2, v3, v4, v5, v6, v7 = struct.unpack("<HHfffffff", payload)
        return {
            "id": int(id_u16),
            "seq": int(seq_u16),
            "v1": float(v1), "v2": float(v2), "v3": float(v3),
            "v4": float(v4), "v5": float(v5), "v6": float(v6), "v7": float(v7),
            "raw_floats": (float(id_u16), float(seq_u16), v1, v2, v3, v4, v5, v6, v7),
            "fmt": "telframe",
        }
    except struct.error:
        pass

    # Legacy: 8 floats
    try:
        f = struct.unpack("<ffffffff", payload)
        id_guess = int(f[0]) & 0xFFFF
        return {
            "id": id_guess,
            "seq": None,
            "v1": float(f[1]), "v2": float(f[2]), "v3": float(f[3]),
            "v4": float(f[4]), "v5": float(f[5]), "v6": float(f[6]), "v7": float(f[7]),
            "raw_floats": f,
            "fmt": "legacy",
        }
    except struct.error:
        return None

# ================== PARSER LÓGICO Y MAPEOS ==================
def _id_hex(id_int: int) -> str:
    return f"0x{id_int:X}"

def parse_telemetry_data_frame(frame_dict: dict):
    """
    Interpreta el frame, actualiza latest_data_dict + data_str,
    y devuelve un Influx Point o None (si Influx no se usa/está caído).
    """
    global data_str, latest_data_dict

    if not frame_dict:
        return None

    id_int = frame_dict["id"]
    id_hex = _id_hex(id_int)
    seq    = frame_dict["seq"]
    v1 = frame_dict["v1"]; v2 = frame_dict["v2"]; v3 = frame_dict["v3"]
    v4 = frame_dict["v4"]; v5 = frame_dict["v5"]; v6 = frame_dict["v6"]; v7 = frame_dict["v7"]

    if seq is not None:
        data_str = (
            f"[RX] ID={id_hex} count={seq}\n"
            f"[RX] FLOATS: {v1:.2f}, {v2:.2f}, {v3:.2f}, {v4:.2f}, {v5:.2f}, {v6:.2f}, {v7:.2f},"
        )
    else:
        data_str = (
            f"[RX] ID={id_hex}\n"
            f"[RX] FLOATS: {v1:.2f}, {v2:.2f}, {v3:.2f}, {v4:.2f}, {v5:.2f}, {v6:.2f}, {v7:.2f},"
        )

    # Base “raw”
    latest_data_dict[id_hex] = {
        "id": id_int, "seq": seq,
        "v1": v1, "v2": v2, "v3": v3, "v4": v4, "v5": v5, "v6": v6, "v7": v7,
    }

    # Mapeos semánticos (ajusta a tu TX real si difiere)
    if id_int == 0x600:
        latest_data_dict[id_hex].update({
            "dc_bus_voltage": v1,
            "dc_bus_power":   v2,
            "rpm":            v3,
            "torque_total":   v4,
            "cell_min_v":     v5,
            "throttle_raw1":  v6,
            "throttle_raw2":  v7,
        })
        # Compat con UI que mira 0x620:
        latest_data_dict["0x620"] = {
            "dc_bus_voltage": v1,
            "dc_bus_power":   v2,
            "motor_temp":     latest_data_dict.get("0x620", {}).get("motor_temp", 0.0),
            "pwrstg_temp":    latest_data_dict.get("0x620", {}).get("pwrstg_temp", 0.0),
        }
    elif id_int == 0x630:
        latest_data_dict[id_hex].update({
            "torque_req": v1,
            "torque_est": v2,
            "throttle":   max(0.0, min(100.0, v3)),
            "brake":      max(0.0, min(100.0, v4)),
        })
    elif id_int == 0x640:
        latest_data_dict[id_hex].update({
            "current_sensor": v1,
            "cell_min_v":     v2,
            "cell_max_temp":  v3,
        })
    elif id_int == 0x680:
        latest_data_dict[id_hex].update({
            "status": v1,
            "errors": v2,
        })

    # Intentar construir un Point (solo si luego se va a usar)
    try:
        from influxdb_client import Point
        pt = (
            Point("telemetry")
            .tag("id_hex", id_hex)
            .field("v1", float(v1))
            .field("v2", float(v2))
            .field("v3", float(v3))
            .field("v4", float(v4))
            .field("v5", float(v5))
            .field("v6", float(v6))
            .field("v7", float(v7))
        )
        if seq is not None:
            pt = pt.field("seq", int(seq))
        return pt
    except Exception:
        # Si la lib no está o falla, seguimos sin Point
        return None

# ================== METADATOS / BUCKET (OPCIONAL) ==================
def write_session_metadata(write_api, bucket_id, piloto, circuito):
    """Escribe metadatos de sesión si hay write_api; si no, no hace nada."""
    if write_api is None:
        return
    try:
        from influxdb_client import Point
        p = (
            Point("session_meta")
            .tag("piloto", piloto)
            .tag("circuito", circuito)
            .field("start_ts", int(time.time()))
        )
        write_api.write(bucket=bucket_id, record=p)
    except Exception as e:
        logger.warning("No se pudo escribir metadatos de sesión: %s", e)

def _ensure_bucket(bucket_name: str) -> str:
    """Crea el bucket si es posible; si no, devuelve el nombre sin fallar."""
    if not _influx_ok or _client is None:
        return bucket_name
    try:
        ba = _client.buckets_api()
        existing = [b for b in (ba.find_buckets().buckets or []) if b.name == bucket_name]
        if not existing:
            ba.create_bucket(bucket_name=bucket_name, org=INFLUX_CONFIG["org"])
        return bucket_name
    except Exception as e:
        logger.warning("No se pudo asegurar bucket '%s': %s", bucket_name, e)
        return bucket_name

def create_bucket(piloto: str, circuito: str, use_influx: bool = INFLUX_ENABLE_DEFAULT) -> str:
    """
    Devuelve un nombre de bucket único por sesión. Si use_influx=True,
    intenta comprobar/crear el bucket, pero nunca lanza excepción.
    """
    global INFLUX_ENABLE_DEFAULT
    INFLUX_ENABLE_DEFAULT = bool(use_influx)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_piloto = piloto.replace(" ", "_")
    safe_circuito = circuito.replace(" ", "_")
    bucket_name = f"ISC_{ts}_{safe_piloto}_{safe_circuito}"

    if use_influx:
        _init_influx()
        bucket_name = _ensure_bucket(bucket_name)

    return bucket_name

def get_latest_data(data_id: str = None):
    if data_id:
        return latest_data_dict.get(data_id, {})
    return latest_data_dict.copy()

# ================== EXCEL LOGGING ==================
class ExcelSessionLogger:
    """Crea/actualiza Excel en ./logs con una fila por frame."""
    def __init__(self, piloto: str, circuito: str):
        os.makedirs("logs", exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_piloto = piloto.replace(" ", "_")
        safe_circuito = circuito.replace(" ", "_")
        self.path = os.path.join("logs", f"ISC_{ts}_{safe_piloto}_{safe_circuito}.xlsx")

        if not os.path.exists(self.path):
            df = pd.DataFrame(columns=["timestamp", "id_hex", "seq", "v1", "v2", "v3", "v4", "v5", "v6", "v7"])
            with pd.ExcelWriter(self.path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="telemetry")

    def append(self, id_hex: str, seq, v1, v2, v3, v4, v5, v6, v7):
        row = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "id_hex": id_hex,
            "seq": seq if seq is not None else -1,
            "v1": v1, "v2": v2, "v3": v3, "v4": v4, "v5": v5, "v6": v6, "v7": v7,
        }
        try:
            # Simple (no óptimo para sesiones MUY largas): lee, concatena, reescribe
            existing = pd.read_excel(self.path, sheet_name="telemetry")
            newdf = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
            with pd.ExcelWriter(self.path, engine="openpyxl", mode="w") as writer:
                newdf.to_excel(writer, index=False, sheet_name="telemetry")
        except Exception as e:
            logger.warning("No se pudo escribir Excel '%s': %s", self.path, e)

# ================== RECEPCIÓN PRINCIPAL ==================
def receive_data(bucket_id: str,
                 piloto: str,
                 circuito: str,
                 port: str = DEFAULT_PORT,
                 baud: int = DEFAULT_BAUD,
                 use_influx: bool = INFLUX_ENABLE_DEFAULT,
                 debug: bool = False):
    """
    Bucle principal:
      - Log inicial estilo Arduino ([CONFIG] + entorno)
      - Emite "Radio Checking" cada 500 ms
      - Lee frames, decodifica, actualiza latest_data_dict + data_str + new_data_flag
      - (Opcional) escribe en Influx
      - Escribe Excel
      - Muestra [STATS] cada 2 s
    """
    global new_data_flag

    # Nivel de log
    if debug:
        logger.setLevel(logging.DEBUG)
    logger.info("Recepción USB-Serial iniciada")

    # Influx opcional
    write_api = None
    if use_influx:
        _init_influx()
        write_api = _get_write_api()
    if write_api:
        write_session_metadata(write_api, bucket_id, piloto, circuito)
    else:
        logger.info("Influx deshabilitado: sólo UI + Excel")

    # Excel
    xlogger = ExcelSessionLogger(piloto, circuito)
    logger.info("[CONFIG] Excel path: %s", xlogger.path)

    # Puerto serie
    if port is None:
        port = _auto_detect_port()
    if port is None:
        raise RuntimeError("No se encontró un puerto serie RF-NANO.")

    ser = _open_serial(port, baud)

    # ===== Mensajes estilo Arduino de configuración esperada =====
    logger.info("[CONFIG] RF24 (esperada por RX):")
    logger.info("        AddressWidth=5, PipeAddr=%s", RF_EXPECTED["PIPE_ADDR"])
    logger.info("        Channel=%d (0x%02X), Payload=%d", RF_EXPECTED["CHANNEL"], RF_EXPECTED["CHANNEL"], RF_EXPECTED["PAYLOAD"])
    logger.info("        DataRate=%s, AutoAck=%s, CRC=%s, PA=%s",
                RF_EXPECTED["DATA_RATE"], "ON" if RF_EXPECTED["AUTO_ACK"] else "OFF",
                RF_EXPECTED["CRC"], RF_EXPECTED["PA"])
    logger.info("[CONFIG] Serial: port=%s, baud=%d, frame=AA 55 %02X <32B> XOR", port, baud, PAYLOAD_LEN)

    # ===== Estadísticas/contadores =====
    counters = {"rx": 0, "decode": 0, "timeout": 0, "len": 0, "short": 0, "chk": 0, "decode_fail": 0}
    last_check_t = time.time()
    last_stats_t = last_check_t
    first_frame_seen = False

    logger.info("Leyendo de %s @ %d bps", port, baud)

    try:
        while new_data_flag != -1:
            now = time.time()
            # "Radio Checking" cada 500 ms
            if now - last_check_t >= 0.5:
                logger.info("Radio Checking")
                last_check_t = now

            payload, err = _read_frame(ser, counters=counters)

            if err == "timeout":
                # tiempo de espera normal, seguimos
                pass
            elif err == "len":
                logger.debug("[ERR] LEN inválida distinta de 32")
            elif err == "short":
                logger.debug("[ERR] Payload corto")
            elif err == "chk":
                logger.debug("[ERR] Checksum XOR no coincide")

            if payload is None:
                # imprimir stats cada 2s aunque no haya frames
                if now - last_stats_t >= 2.0:
                    logger.debug("[STATS] rx=%d decode=%d chk=%d len=%d short=%d timeout=%d decode_fail=%d",
                                 counters["rx"], counters["decode"], counters["chk"],
                                 counters["len"], counters["short"], counters["timeout"], counters["decode_fail"])
                    last_stats_t = now
                continue

            # Tenemos un frame válido
            counters["rx"] += 1
            hexline = _dump_hex(payload)
            logger.debug("[RX] HEX: %s", hexline)

            decoded = _decode_payload(payload)
            if not decoded:
                counters["decode_fail"] += 1
                logger.debug("[ERR] decode_fail (ni TelFrame ni legacy)")
                continue

            counters["decode"] += 1
            if decoded["seq"] is not None:
                logger.debug("[RX] ID=%s SEQ=%d", _id_hex(decoded["id"]), decoded["seq"])
            else:
                logger.debug("[RX] ID=%s (legacy)", _id_hex(decoded["id"]))

            # Parse lógico (y Point si la lib está instalada)
            pt = parse_telemetry_data_frame(decoded)

            # Además del data_str (para la UI), dejamos el detalle debug de floats
            fline = ", ".join(f"{x:.2f}" for x in (
                decoded["v1"], decoded["v2"], decoded["v3"], decoded["v4"],
                decoded["v5"], decoded["v6"], decoded["v7"]))
            logger.debug("[RX] FLOATS: %s", fline)

            # Excel
            id_hex = _id_hex(decoded["id"])
            xlogger.append(
                id_hex,
                decoded.get("seq"),
                decoded["v1"], decoded["v2"], decoded["v3"], decoded["v4"],
                decoded["v5"], decoded["v6"], decoded["v7"]
            )

            # Influx opcional
            if write_api and pt:
                try:
                    pt = pt.tag("piloto", piloto).tag("circuito", circuito)
                    write_api.write(bucket=bucket_id, record=pt)
                except Exception as e:
                    logger.warning("Error escribiendo en Influx: %s", e)

            # Notifica a la UI
            new_data_flag = 1

            if not first_frame_seen:
                first_frame_seen = True
                logger.info("[SYNC] Primer frame recibido correctamente.")

            # stats periódicas cada 2s
            if now - last_stats_t >= 2.0:
                logger.debug("[STATS] rx=%d decode=%d chk=%d len=%d short=%d timeout=%d decode_fail=%d",
                             counters["rx"], counters["decode"], counters["chk"],
                             counters["len"], counters["short"], counters["timeout"], counters["decode_fail"])
                last_stats_t = now

    finally:
        try:
            ser.close()
        except Exception:
            pass
        logger.info("Recepción USB-Serial finalizada.")
