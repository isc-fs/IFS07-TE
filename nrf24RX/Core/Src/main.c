/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Código actualizado para el receptor NRF24 sin usar formato de float
  *                   en printf. Se utiliza una función auxiliar para convertir floats.
  ******************************************************************************
  * @attention
  *
  * Nota: Se ha implementado la función floatToString para evitar el uso de "%.2f".
  * Esto es útil si no se ha habilitado el soporte para formateo de float.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <math.h>
#include "nrf24.h"

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;
SPI_HandleTypeDef hspi2;

/* USER CODE BEGIN PV */
char uart_msg[100];
uint8_t RxAddress[6] = {0xE7, 0xE7, 0xE7, 0xE7, 0xE7};  // Dirección del receptor NRF24
float receivedData[8];  // Buffer para almacenar los datos recibidos (8 floats)
/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);
static void MX_SPI2_Init(void);

/* USER CODE BEGIN PFP */
void print(const char *uart_buffer);
void printHex(uint8_t value);
void printAddress(uint8_t *address, uint8_t size);
void printPayload(float *data, uint8_t size);
void floatToString(float value, char *buffer);
/* USER CODE END PFP */

/* USER CODE BEGIN 0 */
void print(const char *uart_buffer) {
    sprintf(uart_msg, "%s\n\r", uart_buffer);
    HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);
}

void printHex(uint8_t value) {
    sprintf(uart_msg, "%02X ", value);
    HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);
}

void printAddress(uint8_t *address, uint8_t size) {
    for (uint8_t i = 0; i < size; i++) {
        printHex(address[i]);
    }
    print(""); // Salto de línea
}

/* Función auxiliar para convertir un float a cadena sin usar %.2f */
void floatToString(float value, char *buffer) {
    /* Separamos la parte entera y la fracción (dos decimales) */
    if(value < 0) {
        *buffer++ = '-';
        value = -value;
    }
    int intPart = (int)value;
    int fracPart = (int)((value - intPart) * 100); // dos decimales
    sprintf(buffer, "%d.%02d", intPart, fracPart);
}

void printPayload(float *data, uint8_t size) {
    char floatStr[20];
    for (uint8_t i = 0; i < size; i++) {
        floatToString(data[i], floatStr);
        sprintf(uart_msg, "Data[%d]: %s\n\r", i, floatStr);
        HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);
    }
}
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{
  /* MCU Configuration */
  HAL_Init();
  SystemClock_Config();
  MX_GPIO_Init();
  MX_LPUART1_UART_Init();
  MX_SPI2_Init();

  /* NRF24 Inicialización */
  NRF24_Init();
  // Configuramos el receptor en canal 100.
  // (Nota: en NRF24_RxMode se configura el payload para el pipe 2).
  NRF24_RxMode(RxAddress, 100);

  /* Depuración: Imprime la dirección del receptor */
  print("Receiver Address:");
  printAddress(RxAddress, 5);

  /* Bucle principal */
  while (1)
  {
    // Leer el registro STATUS
    uint8_t status = nrf24_ReadReg(STATUS);
    sprintf(uart_msg, "Status: %02X\n\r", status);
    HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);

    // Extraer el número de pipe de los bits 3:1 del registro STATUS
    uint8_t pipe_number = (status >> 1) & 0x07;
    sprintf(uart_msg, "Pipe number: %d\n\r", pipe_number);
    HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);

    // Verificar si hay datos disponibles en el pipe 2 (ya que en NRF24_RxMode se configuró el pipe 2)
    if (isDataAvailable(2))
    {
        // Recibir la carga útil
        NRF24_Receive((uint8_t*)receivedData);

        print("Received Payload:");
        printPayload(receivedData, 8);

        // Se limpia el bit RX_DR del registro STATUS
        nrf24_WriteReg(STATUS, (1 << 6));
    }
    else
    {
        print("No data available");
    }

    // Pequeño retardo para evitar saturar la UART
    HAL_Delay(100);
  }
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV1;
  RCC_OscInitStruct.PLL.PLLN = 16;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief LPUART1 Initialization Function
  * @retval None
  */
static void MX_LPUART1_UART_Init(void)
{
  hlpuart1.Instance = LPUART1;
  hlpuart1.Init.BaudRate = 115200;
  hlpuart1.Init.WordLength = UART_WORDLENGTH_8B;
  hlpuart1.Init.StopBits = UART_STOPBITS_1;
  hlpuart1.Init.Parity = UART_PARITY_NONE;
  hlpuart1.Init.Mode = UART_MODE_TX_RX;
  hlpuart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  hlpuart1.Init.OneBitSampling = UART_ONE_BIT_SAMPLE_DISABLE;
  hlpuart1.Init.ClockPrescaler = UART_PRESCALER_DIV1;
  hlpuart1.AdvancedInit.AdvFeatureInit = UART_ADVFEATURE_NO_INIT;
  if (HAL_UART_Init(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetTxFifoThreshold(&hlpuart1, UART_TXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_SetRxFifoThreshold(&hlpuart1, UART_RXFIFO_THRESHOLD_1_8) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_UARTEx_DisableFifoMode(&hlpuart1) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief SPI2 Initialization Function
  * @retval None
  */
static void MX_SPI2_Init(void)
{
  hspi2.Instance = SPI2;
  hspi2.Init.Mode = SPI_MODE_MASTER;
  hspi2.Init.Direction = SPI_DIRECTION_2LINES;
  hspi2.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi2.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi2.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi2.Init.NSS = SPI_NSS_SOFT;
  hspi2.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;
  hspi2.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi2.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi2.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi2.Init.CRCPolynomial = 7;
  hspi2.Init.CRCLength = SPI_CRC_LENGTH_DATASIZE;
  hspi2.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  if (HAL_SPI_Init(&hspi2) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief GPIO Initialization Function
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  /* Habilitar relojes de los puertos */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* Configurar pines para CSN y CE (NRF24) */
  HAL_GPIO_WritePin(GPIOC, CSN_Pin|CE_Pin, GPIO_PIN_RESET);
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = NRF_IRQ_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(NRF_IRQ_GPIO_Port, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = CSN_Pin|CE_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  __disable_irq();
  while (1)
  {
  }
}

#ifdef  USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line)
{
  /* Informe de error en caso de fallo en assert */
}
#endif /* USE_FULL_ASSERT */
