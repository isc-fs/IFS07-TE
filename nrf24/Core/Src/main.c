/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2024 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "nrf24.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define HEX_CHARS      "0123456789ABCDEF"
/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
UART_HandleTypeDef hlpuart1;

SPI_HandleTypeDef hspi2;

/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_LPUART1_UART_Init(void);
static void MX_SPI2_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
char uart_msg[100];
void print(char uart_buffer[]);
void printValue(float value);
void printHex(uint8_t value);
void generate_data(uint16_t dataid, float* data);
void copyArray(float *source, float *destination, uint8_t size);
float rand_float(float min, float max);
uint8_t chooseRandomNumber(int *array, int size);


uint8_t TxAddress[6] = {0xE7, 0xE7, 0xE7, 0xE7, 0xE7}; //MSB
// Datos a enviar
float data_buffer[8];
uint16_t Id[8] = {1584, 1568, 1552, 1600, 1616, 1632, 1648, 1664};
uint16_t id;
float data1[] = {0x610, 1.23, 4.56, 7.89, 0.12, 3.45, 6.78};
float data2[] = {0x600, 10.11, 12.13, 14.15, 16.17, 18.19, 20.21, 22.23};
float data3[] = {0x630, 23.24, 25.26};
float data4[] = {0x640, 26.27, 28.29, 30.31};
float data5[] = {0x650, 31.32, 33.34, 35.36, 37.38};
float data6[] = {0x670, 38.39, 40.41, 42.43, 44.45};
float data7[] = {0x660, 45.46, 47.48, 49.50, 51.52};
float data8[] = {0x680, 52.53, 54.55, 56.57, 58.59};

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_LPUART1_UART_Init();
  MX_SPI2_Init();
  /* USER CODE BEGIN 2 */

  NRF24_Init();
  NRF24_TxMode(TxAddress, 76);
  NRF24_Dump();

  int i = 0;

  print("Inicializando TX");
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1) {
      HAL_GPIO_TogglePin(GPIOA, GPIO_PIN_5);
      HAL_Delay(300);

      float *data[] = {data1, data2, data3, data4, data5, data6, data7, data8};

      // Mostrar por UART qué se va a enviar
      sprintf(uart_msg, "\r\n[TX] Enviando paquete con ID: 0x%X", (uint16_t)data[i][0]);
      HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);

      for (int j = 1; j < 8; j++) {
          int ent = (int)data[i][j];
          int dec = (int)((data[i][j] - ent) * 100);
          if (dec < 0) dec *= -1;
          sprintf(uart_msg, ", V%d: %d.%02d", j, ent, dec);
          HAL_UART_Transmit(&hlpuart1, (uint8_t*)uart_msg, strlen(uart_msg), HAL_MAX_DELAY);
      }
      HAL_UART_Transmit(&hlpuart1, (uint8_t*)"\r\n", 2, HAL_MAX_DELAY);

      // Enviar por radio
      uint8_t ok = NRF24_Transmit((uint8_t*)data[i]);
      uint8_t st = nrf24_ReadReg(STATUS);
      uint8_t ob = nrf24_ReadReg(OBSERVE_TX);   // [PLOS_CNT | ARC_CNT]

      if (ok) {
          print("[TX] Transmisión exitosa.");
      } else {
          print("[TX] FALLO de transmisión.");
      }

      /* Extra diagnostics */
      sprintf(uart_msg, "STATUS=%02X OBSERVE_TX=%02X\r\n", st, ob);
      HAL_UART_Transmit(&hlpuart1,(uint8_t*)uart_msg,strlen(uart_msg),HAL_MAX_DELAY);


      i++;
      if (i == 8) i = 0;
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

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
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

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
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
  * @param None
  * @retval None
  */
static void MX_LPUART1_UART_Init(void)
{

  /* USER CODE BEGIN LPUART1_Init 0 */

  /* USER CODE END LPUART1_Init 0 */

  /* USER CODE BEGIN LPUART1_Init 1 */

  /* USER CODE END LPUART1_Init 1 */
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
  /* USER CODE BEGIN LPUART1_Init 2 */

  /* USER CODE END LPUART1_Init 2 */

}

/**
  * @brief SPI2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI2_Init(void)
{

  /* USER CODE BEGIN SPI2_Init 0 */

  /* USER CODE END SPI2_Init 0 */

  /* USER CODE BEGIN SPI2_Init 1 */

  /* USER CODE END SPI2_Init 1 */
  /* SPI2 parameter configuration*/
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
  /* USER CODE BEGIN SPI2_Init 2 */

  /* USER CODE END SPI2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
/* USER CODE BEGIN MX_GPIO_Init_1 */
/* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* Idle levels at reset: CSN=HIGH (not selected), CE=LOW */
  HAL_GPIO_WritePin(GPIOC, CSN_Pin, GPIO_PIN_SET);    // CSN HIGH
  HAL_GPIO_WritePin(GPIOC, CE_Pin,  GPIO_PIN_RESET);  // CE  LOW


  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(LD2_GPIO_Port, LD2_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin : B1_Pin */
  GPIO_InitStruct.Pin = B1_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_RISING;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(B1_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pin : NRF_IRQ_Pin */
  GPIO_InitStruct.Pin = NRF_IRQ_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(NRF_IRQ_GPIO_Port, &GPIO_InitStruct);

  /*Configure GPIO pins : CSN_Pin CE_Pin */
  GPIO_InitStruct.Pin = CSN_Pin|CE_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pin : LD2_Pin */
  GPIO_InitStruct.Pin = LD2_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(LD2_GPIO_Port, &GPIO_InitStruct);

/* USER CODE BEGIN MX_GPIO_Init_2 */
/* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void print(char uart_buffer[]){
	sprintf(uart_msg, "%s \n\r", uart_buffer);
	HAL_UART_Transmit(&hlpuart1,(uint8_t*)uart_msg,strlen(uart_msg),HAL_MAX_DELAY);
}

void printValue(float value){
	sprintf(uart_msg, "%.2f \n\r", value); //%hu
	HAL_UART_Transmit(&hlpuart1,(uint8_t*)uart_msg,strlen(uart_msg),HAL_MAX_DELAY);
}

void printHex(uint8_t value){
	sprintf(uart_msg, "%02X ", value);
	HAL_UART_Transmit(&hlpuart1,(uint8_t*)uart_msg,strlen(uart_msg),HAL_MAX_DELAY);
}
// Función para generar un número flotante aleatorio entre min y max
float rand_float(float min, float max) {
    return min + ((float)rand() / RAND_MAX) * (max - min);
}

// Función que escoge un número al azar de un arreglo
uint8_t chooseRandomNumber(int *array, int size) {
    // Inicializar el generador de números aleatorios
    srand(time(NULL));

    // Escoger un índice al azar
    uint8_t randomIndex = (uint8_t) rand() % size;

    // Devolver el número en el índice al azar
    return array[randomIndex];
}

// Función que copia el contenido de un arreglo a otro usando punteros
void copyArray(float *source, float *destination, uint8_t size) {
    for (uint8_t i = 0; i < size; i++) {
        *(destination + i) = *(source + i);
    }
}

void generate_data(uint16_t dataid, float* data) {
    //printf("Data ID: 0x%X\n", dataid);
    uint8_t size = 0;
    switch (dataid) {
        case 0x610: { // IMU REAR
            float data[7] = {dataid, rand_float(-10, 10), rand_float(-10, 10), rand_float(-10, 10), rand_float(-100, 100), rand_float(-100, 100), rand_float(-100, 100)};
            printf("ID: %x, ax: %.2f, ay: %.2f, az: %.2f, GyroX: %.2f, GyroY: %.2f, GyroZ: %.2f\n",
                   (int)data[0], data[1], data[2], data[3], data[4], data[5], data[6]);
            size = 7;
            break;
        }
        case 0x600: { // MOTOR INVERSOR
            float data[7] = {dataid, rand_float(0, 100), rand_float(0, 100), rand_float(0, 100), rand_float(0, 10000), rand_float(0, 400), rand_float(0, 500)};
            int E = rand();
            printf("ID: %x, motor_temp: %.2f, igbt_temp: %.2f, inverter_temp: %.2f, n_actual: %.2f, dc_bus_voltage: %.2f, i_actual: %.2f, E: %d\n",
                   (int)data[0], data[1], data[2], data[3], data[4], data[5], data[6], E);
            size = 7;
            break;
        }
        case 0x630: { // PEDALS
            float data[3] = {dataid, 1, 1};
            //printf("ID: %x, throttle: %.2f, brake: %.2f\n",
                  // (int)data[0], data[1], data[2]);
            size = 3;
            break;
        }
        case 0x640: { // ACUMULADOR
            float data[4] = {dataid, rand_float(0, 500), rand_float(2.5, 4.2), rand_float(20, 60)};
            printf("ID: %x, current_sensor: %.2f, cell_min_v: %.2f, cell_max_temp: %.2f\n",
                   (int)data[0], data[1], data[2], data[3]);
            size = 4;
            break;
        }
        case 0x650: { // GPS
            float data[5] = {dataid, rand_float(0, 200), rand_float(-90, 90), rand_float(-180, 180), rand_float(0, 8000)};
            printf("ID: %x, speed: %.2f, lat: %.2f, long: %.2f, alt: %.2f\n",
                   (int)data[0], data[1], data[2], data[3], data[4]);
            size = 5;
            break;
        }
        case 0x670: { // SUSPENSION
            float data[5] = {dataid, rand_float(0, 100), rand_float(0, 100), rand_float(0, 100), rand_float(0, 100)};
            printf("ID: %x, FR: %.2f, FL: %.2f, RR: %.2f, RL: %.2f\n",
                   (int)data[0], data[1], data[2], data[3], data[4]);
            size = 5;
            break;
        }
        case 0x660: { // INVERTER & MOTOR
            float data[5] = {dataid, rand_float(0, 400), rand_float(0, 400), rand_float(0, 400), rand_float(0, 400)};
            printf("ID: %x, inverter_in: %.2f, inverter_out: %.2f, motor_in: %.2f, motor_out: %.2f\n",
                   (int)data[0], data[1], data[2], data[3], data[4]);
            size = 5;
            break;
        }
        default:
            printf("ID no reconocido: 0x%X\n", dataid);
            break;
    }
    copyArray(data, data_buffer, size);
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
