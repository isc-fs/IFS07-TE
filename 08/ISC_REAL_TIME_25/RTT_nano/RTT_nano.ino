/* rtt_nano.ino  — RF-Nano / nRF24L01+ receiver
 * Forwards each 32-byte radio payload to USB-Serial in a framed binary format:
 *   SOF1(0xAA), SOF2(0x55), LEN(32), PAYLOAD(32B), XOR(payload)
 *
 * Set VERBOSE=1 to also print human-readable diagnostics over Serial.
 */

#include <SPI.h>
#include <RF24.h>
#include "printf.h"

// ------------------ Config ------------------
static const uint8_t PIN_CE  = 10;
static const uint8_t PIN_CSN = 9;
RF24 radio(PIN_CE, PIN_CSN);

static const uint64_t PIPE_ADDR = 0xE7E7E7E7E7ULL;  // must match TX
static const uint8_t  CHANNEL   = 76;               // must match TX
static const uint8_t  PAYLOAD   = 32;               // fixed 32B payload

// Serial framing for Python
static const uint8_t SOF1 = 0xAA;
static const uint8_t SOF2 = 0x55;

// Toggle console verbosity
#define VERBOSE 0   // 0: silent framing only | 1: +HEX dump and radio details

// ------------------ Globals ------------------
uint8_t buf[PAYLOAD];
unsigned long lastCheck = 0;

#if VERBOSE
static void dumpHex(const uint8_t* p, uint8_t n) {
  for (uint8_t i = 0; i < n; ++i) {
    if (i) Serial.print(' ');
    if (p[i] < 16) Serial.print('0');
    Serial.print(p[i], HEX);
  }
}
#endif

// ------------------ Setup ------------------
void setup() {
  Serial.begin(115200);
#if defined(USBCON) || defined(ARDUINO_AVR_LEONARDO)
  while (!Serial) {}   // only needed on native USB boards
#endif

  printf_begin();
#if VERBOSE
  Serial.println(F("Init RF-NANO RX..."));
#endif

  if (!radio.begin()) {
#if VERBOSE
    Serial.println(F("ERR: radio.begin() returned false (chip not detected)."));
#endif
  }

  radio.setAddressWidth(5);
  radio.setChannel(CHANNEL);
  radio.setAutoAck(false);        // NO-ACK (must match TX)
  radio.setDataRate(RF24_1MBPS);  // must match TX
  radio.setCRCLength(RF24_CRC_16);
  radio.setPALevel(RF24_PA_MAX);

  radio.disableDynamicPayloads();
  radio.setPayloadSize(PAYLOAD);
  radio.openReadingPipe(1, PIPE_ADDR);
  radio.startListening();

#if VERBOSE
  radio.printDetails();
  Serial.print(F("Chip conectado: "));
  Serial.println(radio.isChipConnected() ? F("SI") : F("NO"));
  Serial.println(F("RF-NANO RX listo."));
#endif
}

// ------------------ Main loop ------------------
void loop() {
#if VERBOSE
  unsigned long now = millis();
  if (now - lastCheck >= 500) {
    lastCheck = now;
    Serial.println(F("Radio Checking"));
  }
#endif

  if (!radio.available()) return;

  while (radio.available()) {
    radio.read(buf, PAYLOAD);

#if VERBOSE
    // (A) HEX dump
    Serial.print(F("[RX] HEX: "));
    dumpHex(buf, PAYLOAD);
    Serial.println();

    // (B) Decode as 8 floats (for quick eyeballing)
    float f[8];
    memcpy(f, buf, 32); // AVR and STM32 are little-endian IEEE754
    Serial.print(F("[RX] FLOATS: "));
    for (int i = 0; i < 8; ++i) {
      Serial.print(f[i], 2);
      if (i != 7) Serial.print(F(", "));
    }
    Serial.println();

    // (C) Optional: interpret first field as ID (TelFrame.id or legacy f[0])
    uint32_t id = (uint32_t)f[0];
    Serial.print(F("[RX] ID=0x"));
    Serial.println(id, HEX);
#endif

    // ---- Binary frame to Python: AA 55 20 <32 bytes> <xor> ----
    uint8_t xorv = 0;
    for (uint8_t i = 0; i < PAYLOAD; ++i) xorv ^= buf[i];

    Serial.write(SOF1);
    Serial.write(SOF2);
    Serial.write(PAYLOAD);      // length byte
    Serial.write(buf, PAYLOAD); // raw payload (32 bytes)
    Serial.write(xorv);         // XOR checksum of payload
  }
}
