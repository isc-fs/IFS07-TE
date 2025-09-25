/*
  nrf24.c  — STM32H7 HAL driver (polling) for nRF24L01(+)
  Based on ControllersTech, cleaned for H723 + SPI2 + USART2 debug.
*/

#include "nrf24.h"
#include <string.h>
#include <stdio.h>

/* ==== Hardware bindings (edit only if your pins change) ==== */
extern SPI_HandleTypeDef  hspi2;
#define NRF24_SPI        (&hspi2)

extern UART_HandleTypeDef huart2;     /* ECU prints go through USART2 */
#define NRF24_UART       (&huart2)

/* CE / CSN lines */
#define NRF24_CE_PORT    GPIOC
#define NRF24_CE_PIN     GPIO_PIN_3
#define NRF24_CSN_PORT   GPIOC
#define NRF24_CSN_PIN    GPIO_PIN_2

/* ==== Local helpers ====================================================== */
static inline void CS_Select(void)   { HAL_GPIO_WritePin(NRF24_CSN_PORT, NRF24_CSN_PIN, GPIO_PIN_RESET); }
static inline void CS_UnSelect(void) { HAL_GPIO_WritePin(NRF24_CSN_PORT, NRF24_CSN_PIN, GPIO_PIN_SET);   }
static inline void CE_Enable(void)   { HAL_GPIO_WritePin(NRF24_CE_PORT,  NRF24_CE_PIN,  GPIO_PIN_SET);   }
static inline void CE_Disable(void)  { HAL_GPIO_WritePin(NRF24_CE_PORT,  NRF24_CE_PIN,  GPIO_PIN_RESET); }

static void uputs(const char *s){ HAL_UART_Transmit(NRF24_UART, (uint8_t*)s, strlen(s), HAL_MAX_DELAY); }

/* conservative timeouts for H7 @ polling */
#define T_SHORT   100U
#define T_LONG   1000U

/* ==== Low-level SPI access ============================================== */
static void nrf24_WriteReg(uint8_t reg, uint8_t val)
{
    uint8_t buf[2];
    buf[0] = (uint8_t)(W_REGISTER | (reg & REGISTER_MASK));
    buf[1] = val;
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, buf, 2, T_SHORT);
    CS_UnSelect();
}

static void nrf24_WriteRegMulti(uint8_t reg, const uint8_t *data, int size)
{
    uint8_t cmd = (uint8_t)(W_REGISTER | (reg & REGISTER_MASK));
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    HAL_SPI_Transmit(NRF24_SPI, (uint8_t*)data, size, T_LONG);
    CS_UnSelect();
}

static uint8_t nrf24_ReadReg(uint8_t reg)
{
    uint8_t cmd = (uint8_t)(R_REGISTER | (reg & REGISTER_MASK));
    uint8_t val = 0;
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    HAL_SPI_Receive (NRF24_SPI, &val, 1, T_SHORT);
    CS_UnSelect();
    return val;
}

static void nrf24_ReadRegMulti(uint8_t reg, uint8_t *data, int size)
{
    uint8_t cmd = (uint8_t)(R_REGISTER | (reg & REGISTER_MASK));
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    HAL_SPI_Receive (NRF24_SPI, data, size, T_LONG);
    CS_UnSelect();
}

static void nrf24_SendCmd(uint8_t cmd)
{
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    CS_UnSelect();
}

/* ==== Soft reset (subset) =============================================== */
static void nrf24_reset(uint8_t reg)
{
    if (reg == STATUS) {
        /* clear IRQs (RX_DR | TX_DS | MAX_RT) */
        nrf24_WriteReg(STATUS, 0x70);
    }
    else if (reg == FIFO_STATUS) {
        nrf24_WriteReg(FIFO_STATUS, 0x11);
    }
    else {
        /* sensible defaults for bring-up */
        nrf24_WriteReg(CONFIG,      0x08);  /* CRC off, PWR_DOWN */
        nrf24_WriteReg(EN_AA,       0x00);  /* no Auto-ACK */
        nrf24_WriteReg(EN_RXADDR,   0x03);  /* P0,P1 enabled */
        nrf24_WriteReg(SETUP_AW,    0x03);  /* 5-byte addr */
        nrf24_WriteReg(SETUP_RETR,  0x00);  /* no retries */
        nrf24_WriteReg(RF_CH,       76);    /* ch=76 */
        nrf24_WriteReg(RF_SETUP,    0x06);  /* 1 Mbps, 0 dBm */
        nrf24_WriteReg(FEATURE,     0x00);  /* no dyn payloads */
        nrf24_WriteReg(DYNPD,       0x00);
        nrf24_WriteReg(FIFO_STATUS, 0x11);
        nrf24_WriteReg(STATUS,      0x70);  /* clear IRQs */

        uint8_t def0[5] = {0xE7,0xE7,0xE7,0xE7,0xE7};
        uint8_t def1[5] = {0xC2,0xC2,0xC2,0xC2,0xC2};
        nrf24_WriteRegMulti(RX_ADDR_P0, def0, 5);
        nrf24_WriteRegMulti(RX_ADDR_P1, def1, 5);
        nrf24_WriteReg    (RX_ADDR_P2, 0xC3);
        nrf24_WriteReg    (RX_ADDR_P3, 0xC4);
        nrf24_WriteReg    (RX_ADDR_P4, 0xC5);
        nrf24_WriteReg    (RX_ADDR_P5, 0xC6);
        nrf24_WriteRegMulti(TX_ADDR,    def0, 5);

        nrf24_WriteReg(RX_PW_P0, 0);
        nrf24_WriteReg(RX_PW_P1, 0);
        nrf24_WriteReg(RX_PW_P2, 0);
        nrf24_WriteReg(RX_PW_P3, 0);
        nrf24_WriteReg(RX_PW_P4, 0);
        nrf24_WriteReg(RX_PW_P5, 0);
    }
}

/* ==== Public API ========================================================= */

void NRF24_Init(void)
{
    CE_Disable();
    nrf24_reset(0);

    /* fixed settings for link bring-up */
    nrf24_WriteReg(EN_AA,        0x00);  /* NO ACK */
    nrf24_WriteReg(SETUP_RETR,   0x00);  /* NO retries */
    nrf24_WriteReg(EN_RXADDR,    0x03);  /* P0,P1 */
    nrf24_WriteReg(SETUP_AW,     0x03);  /* 5-byte */
    nrf24_WriteReg(RF_CH,        76);    /* channel 76 */
    nrf24_WriteReg(RF_SETUP,     0x06);  /* 1 Mbps, 0 dBm */
    nrf24_WriteReg(FEATURE,      0x00);
    nrf24_WriteReg(DYNPD,        0x00);
    nrf24_WriteReg(FIFO_STATUS,  0x11);
    nrf24_WriteReg(STATUS,       0x70);  /* clear IRQs */

    CE_Enable();    /* power state will be set in TxMode/RxMode */
}

void NRF24_TxMode(uint8_t *Address, uint8_t channel)
{
    CE_Disable();

    nrf24_WriteReg(RF_CH, channel);
    nrf24_WriteRegMulti(TX_ADDR,    Address, 5);
    nrf24_WriteRegMulti(RX_ADDR_P0, Address, 5);  /* ACK return path if enabled later */

    /* CONFIG: PWR_UP(1) | EN_CRC(1) | CRCO(1=16bit) | PRIM_RX(0) */
    uint8_t cfg = (1<<1) | (1<<3) | (1<<2);   /* 0x0E */
    nrf24_WriteReg(CONFIG, cfg);

    CE_Enable();
}

uint8_t NRF24_Transmit(uint8_t *data)   /* 32 bytes */
{
    uint8_t cmd, status;
    uint32_t t0;

    CE_Disable();

    /* load TX FIFO */
    cmd = W_TX_PAYLOAD;
    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    HAL_SPI_Transmit(NRF24_SPI, data, 32, T_LONG);
    CS_UnSelect();

    /* pulse CE >= 10us */
    CE_Enable();
    for (volatile int i = 0; i < 400; i++) { __NOP(); }
    CE_Disable();

    /* wait for TX_DS or MAX_RT, ~5 ms timeout */
    t0 = HAL_GetTick();
    do {
        status = nrf24_ReadReg(STATUS);
        if (status & (1<<5)) break; /* TX_DS */
        if (status & (1<<4)) break; /* MAX_RT */
    } while ((HAL_GetTick() - t0) < 5);

    /* clear IRQ flags */
    nrf24_WriteReg(STATUS, (1<<5) | (1<<4) | (1<<6));

    if (status & (1<<4)) {
        nrf24_SendCmd(FLUSH_TX);
        char msg[64];
        uint8_t ob = nrf24_ReadReg(OBSERVE_TX);
        snprintf(msg, sizeof(msg), "[TX] MAX_RT. STATUS=%02X OBSERVE_TX=%02X\r\n", status, ob);
        HAL_UART_Transmit(NRF24_UART, (uint8_t*)msg, strlen(msg), HAL_MAX_DELAY);
        return 0;
    }
    return (status & (1<<5)) ? 1 : 0;
}

void NRF24_RxMode(uint8_t *Address, uint8_t channel)
{
    CE_Disable();

    nrf24_reset(STATUS);
    nrf24_WriteReg(RF_CH, channel);

    /* enable pipe 2 too (example) */
    uint8_t en = nrf24_ReadReg(EN_RXADDR);
    en |= (1<<2);
    nrf24_WriteReg(EN_RXADDR, en);

    /* Pipe1 carries the MSBytes for P2..P5 */
    nrf24_WriteRegMulti(RX_ADDR_P1, Address, 5);
    nrf24_WriteReg(RX_ADDR_P2, 0xEE);

    nrf24_WriteReg(RX_PW_P2, 32);

    /* CONFIG: PWR_UP | PRIM_RX */
    uint8_t cfg = nrf24_ReadReg(CONFIG);
    cfg |= (1<<1) | (1<<0);
    nrf24_WriteReg(CONFIG, cfg);

    CE_Enable();
}

uint8_t NRF24_IsDataAvailable(int pipenum)
{
    uint8_t st = nrf24_ReadReg(STATUS);
    if ((st & (1<<6)) && (st & (pipenum << 1))) {
        nrf24_WriteReg(STATUS, (1<<6));   /* clear RX_DR */
        return 1;
    }
    return 0;
}

void NRF24_Receive(uint8_t *data)
{
    uint8_t cmd = R_RX_PAYLOAD;

    CS_Select();
    HAL_SPI_Transmit(NRF24_SPI, &cmd, 1, T_SHORT);
    HAL_SPI_Receive (NRF24_SPI, data, 32, T_LONG);
    CS_UnSelect();

    HAL_Delay(1);
    nrf24_SendCmd(FLUSH_RX);
}

/* Read a snapshot of interesting registers into 'data' (38 bytes). */
void NRF24_ReadAll(uint8_t *data)
{
    for (int i = 0; i < 10; i++)  data[i] = nrf24_ReadReg(i);
    nrf24_ReadRegMulti(RX_ADDR_P0, data + 10, 5);
    nrf24_ReadRegMulti(RX_ADDR_P1, data + 15, 5);

    data[20] = nrf24_ReadReg(RX_ADDR_P2);
    data[21] = nrf24_ReadReg(RX_ADDR_P3);
    data[22] = nrf24_ReadReg(RX_ADDR_P4);
    data[23] = nrf24_ReadReg(RX_ADDR_P5);

    nrf24_ReadRegMulti(RX_ADDR_P0, data + 24, 5);

    for (int i = 29; i < 38; i++) data[i] = nrf24_ReadReg(i - 12);
}

/* ===== Simple UART dump ================================================== */
static void hex1(const char *name, uint8_t v){
    char s[32];
    snprintf(s, sizeof(s), "%s=%02X ", name, v);
    uputs(s);
}

static void dump_hex5(const char *name, const uint8_t *v){
    char s[64];
    snprintf(s, sizeof(s), "%s=%02X %02X %02X %02X %02X  ",
            name, v[0], v[1], v[2], v[3], v[4]);
    uputs(s);
}

void NRF24_Dump(void)
{
    uint8_t v, addr[5];
    v = nrf24_ReadReg(CONFIG);     hex1("CFG",   v);
    v = nrf24_ReadReg(EN_AA);      hex1("EN_AA", v);
    v = nrf24_ReadReg(SETUP_RETR); hex1("RETR",  v);
    v = nrf24_ReadReg(RF_CH);      hex1("CH",    v);
    v = nrf24_ReadReg(RF_SETUP);   hex1("RF",    v);
    v = nrf24_ReadReg(FEATURE);    hex1("FEAT",  v);
    v = nrf24_ReadReg(DYNPD);      hex1("DYNPD", v);

    nrf24_ReadRegMulti(TX_ADDR,    addr, 5); dump_hex5("TX",  addr);
    nrf24_ReadRegMulti(RX_ADDR_P0, addr, 5); dump_hex5("RX0", addr);

    v = nrf24_ReadReg(STATUS);     hex1("STAT",  v);
    uputs("\r\n");
}
