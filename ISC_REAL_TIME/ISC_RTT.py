"""
Sistema de Recepción de Telemetría para Formula Student
Recibe datos via NRF24L01+ y los almacena en InfluxDB
"""

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import requests
import pigpio
from nrf24 import *
import time
from datetime import datetime
import struct
import traceback
import sys
import logging
from typing import Dict, Any, Optional

# Configuración de logging para mejor debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cliente InfluxDB - Configuración centralizada
INFLUX_CONFIG = {
    "url": "http://localhost:8086",
    "token": "c2nq6YUcVjUyjVe2-ySQSKB2tgZGIsXCB6ka1BGfR69b1oSx_WA22qHQQp2vtq7whc1pOFcBq1RZnpct1Pgx8g==",
    "org": "b2b03940375e28ac"
}

client = InfluxDBClient(**INFLUX_CONFIG)

# Variables globales para comunicación entre threads
data_str = ""  # String formateado con los últimos datos recibidos
new_data_flag = 0  # Flag: 0=sin datos, 1=datos nuevos, -1=parar recepción
latest_data_dict = {}  # Diccionario con los últimos valores por ID

# Configuración NRF24L01+
NRF_CONFIG = {
    "ce_pin": 25,
    "payload_size": RF24_PAYLOAD.DYNAMIC,
    "channel": 100,
    "data_rate": RF24_DATA_RATE.RATE_2MBPS,
    "pa_level": RF24_PA.MIN,
    "address": [0xE7, 0xE7, 0xE7, 0xE7, 0xE7]
}

def parse_telemetry_data(values: list) -> Optional[Point]:
    """
    Parsea los datos de telemetría según el ID y crea un Point para InfluxDB
    
    Args:
        values: Lista de 8 valores float del payload NRF24
        
    Returns:
        Point de InfluxDB o None si ID no reconocido
    """
    global data_str, latest_data_dict
    
    dataid = int(values[0])
    
    # Diccionario de configuración para cada sensor
    sensor_configs = {
        0x600: {  # IMU TRASERA
            "name": "IMU_REAR",
            "fields": ["ax", "ay", "az", "wx", "wy", "wz"],
            "format_str": "IMU REAR - ax:{:.2f} ay:{:.2f} az:{:.2f} wx:{:.2f} wy:{:.2f} wz:{:.2f}"
        },
        0x610: {  # IMU DELANTERA
            "name": "IMU_FRONT", 
            "fields": ["ax", "ay", "az", "wx", "wy", "wz"],
            "format_str": "IMU FRONT - ax:{:.2f} ay:{:.2f} az:{:.2f} wx:{:.2f} wy:{:.2f} wz:{:.2f}"
        },
        0x620: {  # TREN DE POTENCIA
            "name": "POWERTRAIN",
            "fields": ["motor_temp", "pwrstg_temp", "board1_temp", "board2_temp", "dc_bus_voltage", "dc_bus_power", "motor_rpm"],
            "format_str": "POWERTRAIN - Temp Motor:{:.1f}°C Temp Stage:{:.1f}°C DC Bus:{:.1f}V Potencia:{:.1f}W RPM:{:.0f}"
        },
        0x630: {  # ENTRADAS DEL PILOTO
            "name": "DRIVER_INPUTS",
            "fields": ["throttle", "brake", "torque_req", "torque_est"],
            "format_str": "DRIVER - Acelerador:{:.1f}% Freno:{:.1f}% Torque Req:{:.1f}Nm Torque Est:{:.1f}Nm"
        },
        0x640: {  # ACUMULADOR
            "name": "ACCUMULATOR",
            "fields": ["current_sensor", "cell_min_v", "cell_max_temp"],
            "format_str": "ACCU - Corriente:{:.1f}A Voltaje Min:{:.2f}V Temp Max:{:.1f}°C"
        },
        0x650: {  # GPS
            "name": "GPS",
            "fields": ["speed", "lat", "long", "alt"],
            "format_str": "GPS - Velocidad:{:.1f}km/h Lat:{:.6f} Long:{:.6f} Alt:{:.1f}m"
        },
        0x660: {  # SUSPENSIÓN
            "name": "SUSPENSION",
            "fields": ["FR", "FL", "RR", "RL"],
            "format_str": "SUSPENSIÓN - FR:{:.2f} FL:{:.2f} RR:{:.2f} RL:{:.2f}"
        },
        0x670: {  # TEMPERATURAS DE AGUA
            "name": "WATER_TEMPS",
            "fields": ["inverter_in", "inverter_out", "motor_in", "motor_out"],
            "format_str": "AGUA - Inv In:{:.1f}°C Inv Out:{:.1f}°C Motor In:{:.1f}°C Motor Out:{:.1f}°C"
        },
        0x680: {  # ESTADO DEL INVERSOR
            "name": "INVERTER_STATUS",
            "fields": ["status", "errors"],
            "format_str": "INVERSOR - Estado:{:.0f} Errores:{:.0f}"
        }
    }
    
    if dataid in sensor_configs:
        config = sensor_configs[dataid]
        
        # Crear Point para InfluxDB
        point = Point(config["name"])
        
        # Añadir campos al point y actualizar diccionario global
        sensor_data = {}
        for i, field in enumerate(config["fields"]):
            if i + 1 < len(values):  # Verificar que el índice existe
                value = values[i + 1]
                point = point.field(field, value)
                sensor_data[field] = value
        
        # Actualizar diccionario global con últimos datos
        latest_data_dict[hex(dataid)] = sensor_data
        
        # Formatear string para mostrar
        try:
            format_values = [values[i + 1] for i in range(len(config["fields"])) if i + 1 < len(values)]
            data_str = config["format_str"].format(*format_values)
        except (IndexError, ValueError) as e:
            data_str = f"Error formateando datos {hex(dataid)}: {e}"
            logger.warning(data_str)
        
        return point
    else:
        data_str = f"ID DESCONOCIDO: {hex(dataid)}"
        logger.warning(data_str)
        return None

def initialize_nrf24(pi: pigpio.pi) -> NRF24:
    """
    Inicializa y configura el módulo NRF24L01+
    
    Args:
        pi: Instancia de pigpio
        
    Returns:
        Objeto NRF24 configurado
    """
    try:
        nrf = NRF24(pi, ce=NRF_CONFIG["ce_pin"], 
                   payload_size=NRF_CONFIG["payload_size"],
                   channel=NRF_CONFIG["channel"],
                   data_rate=NRF_CONFIG["data_rate"],
                   pa_level=NRF_CONFIG["pa_level"])
        
        # Configurar dirección
        nrf.set_address_bytes(len(NRF_CONFIG["address"]))
        nrf.open_reading_pipe(RF24_RX_ADDR.P1, NRF_CONFIG["address"])
        
        logger.info("NRF24L01+ inicializado correctamente")
        nrf.show_registers()
        
        return nrf
        
    except Exception as e:
        logger.error(f"Error inicializando NRF24L01+: {e}")
        raise

def receive_data(bucket_id: str, piloto: str, circuito: str) -> None:
    """
    Función principal de recepción de datos
    Recibe datos del NRF24L01+ y los envía a InfluxDB
    
    Args:
        bucket_id: ID del bucket de InfluxDB donde guardar los datos
        piloto: Nombre del piloto (para metadatos)
        circuito: Nombre del circuito (para metadatos)
    """
    global new_data_flag
    
    logger.info("Iniciando recepción de datos...")
    
    # Inicializar pigpio
    pi = pigpio.pi()
    if not pi.connected:
        logger.error("No se pudo conectar a pigpio")
        return
    
    nrf = None
    write_api = None
    
    try:
        # Inicializar NRF24 y InfluxDB
        nrf = initialize_nrf24(pi)
        write_api = client.write_api(write_options=SYNCHRONOUS)
        
        # Escribir metadatos de la sesión
        write_session_metadata(write_api, bucket_id, piloto, circuito)
        
        logger.info(f"Recibiendo desde: {NRF_CONFIG['address']}")
        packet_count = 0
        
        # Bucle principal de recepción
        while new_data_flag != -1:  # -1 es la señal para parar
            
            # Procesar todos los paquetes disponibles
            while nrf.data_ready() and new_data_flag != -1:
                packet_count += 1
                
                try:
                    payload = nrf.get_payload()
                    
                    # Verificar tamaño del payload (8 floats = 32 bytes)
                    if len(payload) == 32:
                        # Desempaquetar 8 valores float (little endian)
                        values = struct.unpack("<ffffffff", payload)
                        
                        # Parsear datos y crear point
                        point = parse_telemetry_data(values)
                        
                        if point:
                            # Añadir timestamp y metadatos
                            point = point.tag("piloto", piloto).tag("circuito", circuito)
                            
                            # Escribir a InfluxDB
                            write_api.write(bucket=bucket_id, record=point)
                            
                            # Señalar que hay nuevos datos para la UI
                            new_data_flag = 1
                            
                        else:
                            logger.warning(f"Datos no reconocidos en paquete {packet_count}")
                    
                    else:
                        logger.warning(f"Tamaño de payload incorrecto: {len(payload)} bytes (esperado: 32)")
                        
                except struct.error as e:
                    logger.error(f"Error desempaquetando datos: {e}")
                except Exception as e:
                    logger.error(f"Error procesando paquete {packet_count}: {e}")
            
            # Pequeña pausa para no saturar la CPU
            time.sleep(0.001)
            
    except KeyboardInterrupt:
        logger.info("Recepción interrumpida por el usuario")
    except Exception as e:
        logger.error(f"Error en recepción de datos: {e}")
        traceback.print_exc()
    finally:
        # Limpieza
        if nrf:
            nrf.power_down()
        if pi:
            pi.stop()
        logger.info(f"Recepción finalizada. Paquetes procesados: {packet_count}")

def write_session_metadata(write_api, bucket_id: str, piloto: str, circuito: str) -> None:
    """
    Escribe metadatos de la sesión en InfluxDB
    
    Args:
        write_api: API de escritura de InfluxDB
        bucket_id: ID del bucket
        piloto: Nombre del piloto
        circuito: Nombre del circuito
    """
    try:
        # Metadatos de piloto
        pilot_point = Point("session_metadata").tag("type", "pilot").field("name", piloto)
        write_api.write(bucket=bucket_id, record=pilot_point)
        
        # Metadatos de circuito
        circuit_point = Point("session_metadata").tag("type", "circuit").field("name", circuito)
        write_api.write(bucket=bucket_id, record=circuit_point)
        
        logger.info(f"Metadatos escritos: Piloto={piloto}, Circuito={circuito}")
        
    except Exception as e:
        logger.error(f"Error escribiendo metadatos: {e}")

def get_user_input() -> tuple:
    """
    Solicita al usuario el nombre del piloto y circuito
    
    Returns:
        Tupla (piloto, circuito)
    """
    piloto = input("Introducir el nombre del piloto: ").strip()
    circuito = input("Introducir el nombre del circuito: ").strip()
    
    if not piloto or not circuito:
        logger.warning("Nombre de piloto o circuito vacío")
    
    return piloto, circuito

def create_bucket(piloto: str, circuito: str) -> str:
    """
    Crea un nuevo bucket en InfluxDB para la sesión
    
    Args:
        piloto: Nombre del piloto
        circuito: Nombre del circuito
        
    Returns:
        ID del bucket creado
    """
    headers = {
        'Authorization': f'Token {INFLUX_CONFIG["token"]}',
        'Content-Type': 'application/json'
    }
    
    url = f'{INFLUX_CONFIG["url"]}/api/v2/buckets'
    
    # Generar nombre único con timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    bucket_name = f"{timestamp}_FS-{circuito}-{piloto}"
    
    payload = {
        "orgID": INFLUX_CONFIG["org"],
        "name": bucket_name,
        "description": f"Sesión de telemetría: {piloto} en {circuito}",
        "retentionRules": []  # Sin expiración
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        
        # Extraer ID del bucket de la respuesta
        bucket_data = response.json()
        bucket_id = bucket_data.get('id')
        
        if bucket_id:
            logger.info(f"Bucket creado: {bucket_name} (ID: {bucket_id})")
            return bucket_id
        else:
            raise ValueError("No se pudo obtener el ID del bucket")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creando bucket: {e}")
        raise
    except ValueError as e:
        logger.error(f"Error procesando respuesta del bucket: {e}")
        raise

def get_latest_data(data_id: str = None) -> Dict[str, Any]:
    """
    Obtiene los últimos datos recibidos
    
    Args:
        data_id: ID específico de datos (opcional)
        
    Returns:
        Diccionario con los últimos datos
    """
    if data_id:
        return latest_data_dict.get(data_id, {})
    return latest_data_dict.copy()

if __name__ == "__main__":
    """
    Función principal - solo se ejecuta si el script se ejecuta directamente
    """
    print("=== Sistema de Recepción NRF24 ISC ===")
    
    try:
        while True:
            # Obtener datos del usuario
            piloto, circuito = get_user_input()
            
            if not piloto or not circuito:
                print("Piloto y circuito son obligatorios. Inténtalo de nuevo.")
                continue
            
            # Crear bucket para la sesión
            try:
                bucket_id = create_bucket(piloto, circuito)
                print(f"Bucket creado con ID: {bucket_id}")
                
                # Iniciar recepción
                receive_data(bucket_id, piloto, circuito)
                
            except Exception as e:
                logger.error(f"Error en la sesión: {e}")
                break
                
    except KeyboardInterrupt:
        print("\nSistema detenido por el usuario")
    except Exception as e:
        logger.error(f"Error fatal: {e}")
