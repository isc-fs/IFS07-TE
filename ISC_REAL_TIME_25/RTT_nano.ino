/* RF-NANO receiver -> USB Serial forwarder (32B frames)
 * Requisitos: RF24 by TMRh20 (Arduino Library Manager)
 * Dirección RF: 0xE7E7E7E7E7, Canal: 100, DataRate: 2Mbps, Payload: 32
 * Serie: 115200 8N1
 */

#include <SPI.h>
#include <RF24.h>

// Pines del RF-NANO (según placa: CE=D10, CSN=D9 en este modelo)
static const uint8_t PIN_CE  = 10;
static const uint8_t PIN_CSN = 9;

RF24 radio(PIN_CE, PIN_CSN);

// Dirección y configuración RF
static const uint64_t PIPE_ADDR = 0xE7E7E7E7E7LL; // 5 bytes efectivos
static const uint8_t  CHANNEL   = 100;           // 0x64
static const uint8_t  PAYLOAD   = 32;            // 8 floats

// Encapsulado serie
static const uint8_t SOF1 = 0xAA;
static const uint8_t SOF2 = 0x55;

uint8_t buf[PAYLOAD];

void setup() {
  // USB-Serial
  Serial.begin(115200);
  while (!Serial) { /* esperar si es necesario */ }

  // RF24
  if (!radio.begin()) {
    Serial.println(F("ERR: radio.begin()"));
  }

  radio.setChannel(CHANNEL);
  radio.setAutoAck(false);           // El TX STM no envía NO_ACK explícito; desactiva ACK por robustez
  radio.setDataRate(RF24_2MBPS);     // 2 Mbps
  radio.setCRCLength(RF24_CRC_16);   // CRC en RF (opcional)
  radio.setPALevel(RF24_PA_MIN);     // Ajustable (ver sección potencia en datasheet). :contentReference[oaicite:3]{index=3}
  radio.disableDynamicPayloads();    // Forzamos tamaño fijo
  radio.setPayloadSize(PAYLOAD);
  radio.openReadingPipe(1, PIPE_ADDR);
  radio.startListening();

  Serial.println(F("RF-NANO RX listo (CH=100, 2Mbps, 32B)."));
}

void loop() {
  while (radio.available()) {
    radio.read(buf, PAYLOAD);
    // Calcular checksum XOR
    uint8_t chk = 0;
    for (uint8_t i = 0; i < PAYLOAD; ++i) chk ^= buf[i];

    // Enviar frame a PC
    Serial.write(SOF1);
    Serial.write(SOF2);
    Serial.write(PAYLOAD);
    Serial.write(buf, PAYLOAD);
    Serial.write(chk);
  }
}
