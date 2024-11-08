from ast import NotIn
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


client = InfluxDBClient(url="http://localhost:8086",
                        token="c2nq6YUcVjUyjVe2-ySQSKB2tgZGIsXCB6ka1BGfR69b1oSx_WA22qHQQp2vtq7whc1pOFcBq1RZnpct1Pgx8g==",
                        org="b2b03940375e28ac")


data_str = ""
new_data_flag = 0

# Function to receive data


def receive_data(bucketnever, piloto, circuito):
    print("Starting data reception...")

    # Initialize the pigpio library
    pi = pigpio.pi()

    if not pi.connected:
        print("Could not connect to pigpio")
        exit()
    nrf = NRF24(pi, ce=25, payload_size=RF24_PAYLOAD.DYNAMIC, channel=100,
                data_rate=RF24_DATA_RATE.RATE_2MBPS, pa_level=RF24_PA.MIN)

    # Set the RX and TX addresses
    address = [0xE7, 0xE7, 0xE7, 0xE7, 0xE7]
    nrf.set_address_bytes(len(address))

    # Configure RX pipes
    nrf.open_reading_pipe(RF24_RX_ADDR.P1, address)

    nrf.show_registers()

    write_api = client.write_api(write_options=SYNCHRONOUS)

    try:
        print(f'Receive from: {address}')
        count = 0
        global new_data_flag
        while new_data_flag != -1:  # señal para parar recepción

            while nrf.data_ready() and new_data_flag != -1:

                count += 1
                payload = nrf.get_payload()
                # añado calculo de tiempo para poder añadir un timestamp a cada id de datos
                current_time = datetime.now().strftime("%d:%m:%Y-%H:%M")

                if len(payload) == 32:
                    values = struct.unpack("<ffffffff", payload)
                    global data_str
                    data_str = ""
                    dataid = values[0]

                    if dataid == 0x600:  # IMU REAR
                        data_str = f'ID: {hex(int(values[0]))}, ax: {round(values[1],2)}, ay: {round(values[2],2)}, az: {round(values[3],2)}, GyroX: {round(values[4],2)}, GyroY: {round(values[5],2)}, GyroZ: {round(values[6],2)}'
                        print(data_str)
                        p = Point("0x600").field("ax", values[1]).field("ay", values[2]).field(
                            "az", values[3]).field("wx", values[4]).field("wy", values[5]).field("wz", values[6])
                    elif dataid == 0x610:  # IMU FRONT
                        data_str = f'ID: {hex(int(values[0]))}, ax: {round(values[1],2)}, ay: {round(values[2],2)}, az: {round(values[3],2)}, GyroX: {round(values[4],2)}, GyroY: {round(values[5],2)}, GyroZ: {round(values[6],2)}, E: {values[7]}'
                        print(data_str)
                        p = Point("0x610").field("ax", values[1]).field("ay", values[2]).field(
                            "az", values[3]).field("wx", values[4]).field("wy", values[5]).field("wz", values[6])
                    elif dataid == 0x620:  # POWERTRAIN
                        data_str = f'ID: {hex(int(values[0]))}, motor_temp: {round(values[1],2)}, pwrstg_temp: {round(values[2],2)}, board1_temp: {round(values[3],2)}, board2_temp: {round(values[4],2)}, dc_bus_voltage: {round(values[5],2)}, dc_bus_power: {round(values[6],2)}, motor_rpm: {values[7]}'
                        print(data_str)
                        p = Point("0x620").field("motor_temp", values[1]).field("pwrstg_temp", values[2]).field("board1_temp", values[3]).field(
                            "board2_temp", values[4]).field("dc_bus_voltage", values[5]).field("dc_bus_power", values[6]).field("motor_rpm", values[7])
                    elif dataid == 0x630:  # DRIVER INPUTS
                        data_str = f'ID: {hex(int(values[0]))}, throttle: {round(values[1],2)}, brake: {round(values[2],2)}, torque_req: {round(values[3],2)}, torque_est:{round(values[4],2)}'
                        print(data_str)
                        p = Point("0x630").field("throttle", values[1]).field("brake", values[2]).field(
                            "torque_req", values[3]).field("torque_est", values[4])
                    elif dataid == 0x640:  # ACUMULADOR
                        data_str = f'ID: {hex(int(values[0]))}, current_sensor: {round(values[1],2)}, cell_min_v: {round(values[2],2)}, cell_max_temp: {round(values[3],2)}'
                        print(data_str)
                        p = Point("0x640").field("current_sensor", values[1]).field(
                            "cell_min_v", values[2]).field("cell_max_temp", values[3])
                    elif dataid == 0x650:  # GPS
                        data_str = f'ID: {hex(int(values[0]))}, speed: {round(values[1],2)}, lat: {round(values[2],2)}, long: {round(values[3],2)},alt: {round(values[3],2)}'
                        print(data_str)
                        p = Point("0x650").field("speed", values[1]).field(
                            "lat", values[2]).field("long", values[3]).field("alt", values[3])
                    elif dataid == 0x660:  # SUSPENSION
                        data_str = f'ID: {hex(int(values[0]))}, FR: {round(values[1],2)}, FL: {round(values[2],2)}, RR: {round(values[3],2)}, RL: {round(values[4],2)}'
                        print(data_str)
                        p = Point("0x660").field("Suspension_FR", values[1]).field("Suspension_FL", values[2]).field(
                            "Suspension_RR", values[3]).field("Suspension_RL", values[4])
                    elif dataid == 0x670:  # WATER TEMPERATURES
                        data_str = f'ID: {hex(int(values[0]))}, inverter_in: {round(values[1],2)}, inverter_out: {round(values[2],2)}, motor_in: {round(values[3],2)}, motor_out: {round(values[4],2)}'
                        print(data_str)
                        p = Point("0x670").field("Inverter_inlet", values[1]).field(
                            "Inverter_outlet", values[2]).field("Motor_inlet", values[3]).field("Motor_outlet", values[4])
                    elif dataid == 0x680:  # INVERTER STATUS AND ERRORS
                        p = Point("0x680").field("Inverter_status",
                                                 values[1]).field("dem", values[2])
                        data_str = f'ID:{hex(int(values[0]))}, status: {int(values[1])}, dem: {int(values[2])}'
                        print(data_str)
                    else:
                        p = "CAMBIAR ESTO"
                        data_str = f'ID: {hex(int(values[0]))}'
                        print(data_str)
                # global new_data_flag
                new_data_flag = 1
                write_api.write(bucket=bucketnever, record=p)
                # write_api.write(bucket=bucket, record=p)
                bucket = "CAMBIAR ESTO CUANDO ESTÉ CONFIGURADO"
                writerundata(bucketnever, bucket, piloto, circuito)

    except:
        traceback.print_exc()
        nrf.power_down()
        pi.stop()


def writerundata(bucketnever, bucket, piloto, circuito):
    write_api = client.write_api(write_options=SYNCHRONOUS)

    p = Point("piloto").field("data", piloto)
    write_api.write(bucket=bucketnever, record=p)
    # write_api.write(bucket=bucket, record=p)

    p = Point("circuito").field("data", circuito)
    write_api.write(bucket=bucketnever, record=p)
    # write_api.write(bucket=bucket, record=p)


def rundata():

    piloto = input("Introducir el nombre del piloto: ")
    circuito = input("Introducir el nombre del circuito: ")

    return piloto, circuito


def createbucket(piloto, circuito):
    headers = {'Authorization': 'Token c2nq6YUcVjUyjVe2-ySQSKB2tgZGIsXCB6ka1BGfR69b1oSx_WA22qHQQp2vtq7whc1pOFcBq1RZnpct1Pgx8g=='}
    url = "http://localhost:8086/api/v2/buckets"
    payloadtemp = {
        "orgID": "b2b03940375e28ac",
        "name": "ISC",
        "description": "create a bucket",
        "rp": "myrp",
        "retentionRules": [
            {
                "type": "expire",
                "everySeconds": 86400
            }
        ]
    }

    test = datetime.now()
    time = test.strftime("%Y-%m-%d %H:%M:%S")
    print(time)

    payloadnever = {
        "orgID": "b2b03940375e28ac",
        "name": time+" |> FS-"+circuito+"-"+piloto,
        "description": "create a bucket",
        "rp": "myrp",
        "duration": "INF"
    }

    # "type": "expire","everySeconds": 86400 // es 1 dia
    # Para crear un rp que no se borre quitas retentionRules y pones "duration": "INF"
    # No se puede crear un bucket con el mismo nombre que uno ya existente

    r1 = requests.post(url, headers=headers, json=payloadnever)
    r2 = requests.post(url, headers=headers, json=payloadtemp)
    # print(r.text.split(",")[0].split(":")[1].replace('"',"").replace(" ",""))
    # print(r.text)
    return r1.text.split(",")[0].split(":")[1].replace('"', "").replace(" ", "")
    # r.text.split(",")[0].split(":")[1].replace('"',"").replace(" ","") de aqui sacas el id del bucket creado


if __name__ == "__main__":  # metido en main para evitar que se ejecute al importar
    print("Raspberry Pi NRF24 Receiver is online.")
    while True:

        piloto, circuito = rundata()

        bucketnever = createbucket(piloto, circuito)
        bucket = "296f7f6218c651a2"
        print(f"Bucket created with ID - {bucketnever} | {bucket}")

        # rxnrf24(bucketnever,piloto,circuito)
        receive_data(bucketnever, piloto, circuito)

        # time.sleep(0.1)
