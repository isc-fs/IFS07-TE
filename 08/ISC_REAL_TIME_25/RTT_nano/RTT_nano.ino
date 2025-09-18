#include <SPI.h>
#include <RF24.h>
#include "printf.h"

static const uint8_t PIN_CE  = 10;
static const uint8_t PIN_CSN = 9;
RF24 radio(PIN_CE, PIN_CSN);

static const uint64_t PIPE_ADDR = 0xE7E7E7E7E7ULL;
static const uint8_t  CHANNEL   = 76;   // 0x4C
static const uint8_t  PAYLOAD   = 32;   // 8 floats

uint8_t buf[PAYLOAD];
unsigned long lastCheck = 0;

static void dumpHex(const uint8_t* p, uint8_t n) {
  for (uint8_t i = 0; i < n; ++i) {
    if (i) Serial.print(' ');
    if (p[i] < 16) Serial.print('0');
    Serial.print(p[i], HEX);
  }
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  printf_begin();
  Serial.println(F("Init RF-NANO RX..."));

  if (!radio.begin()) {
    Serial.println(F("ERR: radio.begin() returned false (chip not detected)."));
  }

  radio.setAddressWidth(5);
  radio.setChannel(CHANNEL);
  radio.setAutoAck(false);          // NO-ACK
  radio.setDataRate(RF24_1MBPS);    // 1 Mbps to match STM
  radio.setCRCLength(RF24_CRC_16);
  radio.setPALevel(RF24_PA_MAX);

  radio.disableDynamicPayloads();
  radio.setPayloadSize(PAYLOAD);
  radio.openReadingPipe(1, PIPE_ADDR);
  radio.startListening();

  radio.printDetails();
  Serial.print(F("Chip conectado: "));
  Serial.println(radio.isChipConnected() ? F("SI") : F("NO"));
  Serial.println(F("RF-NANO RX listo."));
}

void loop() {
  unsigned long now = millis();
  if (now - lastCheck >= 500) {
    lastCheck = now;
    Serial.println(F("Radio Checking"));
  }

  if (radio.available()) {
    while (radio.available()) {
      radio.read(buf, PAYLOAD);

      // ---------- (A) HEX DUMP ----------
      Serial.print(F("[RX] HEX: "));
      dumpHex(buf, PAYLOAD);
      Serial.println();

      // ---------- (B) DECODE AS 8 FLOATS ----------
      float f[8];
      memcpy(f, buf, 32); // AVR and STM32 are little-endian IEEE754
      Serial.print(F("[RX] FLOATS: "));
      for (int i = 0; i < 8; ++i) {
        Serial.print(f[i], 2);
        if (i != 7) Serial.print(F(", "));
      }
      Serial.println();

      // ---------- (C) OPTIONAL: treat first float as ID ----------
      uint32_t id = (uint32_t)f[0];
      Serial.print(F("[RX] ID=0x"));
      Serial.println(id, HEX);
    }
  }
}
