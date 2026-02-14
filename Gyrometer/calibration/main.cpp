/*
 * HMC5883L Magnetometer Calibration Tool
 * =======================================
 * Flash this firmware to collect min/max readings from the magnetometer.
 *
 * Usage:
 *   1. Flash:   pio run -e calibration -t upload
 *   2. Monitor: pio device monitor
 *   3. Slowly rotate the sensor through ALL orientations for 30–60 seconds.
 *      (Think: tumble it gently in every direction — pitch, roll, yaw.)
 *   4. When you're happy with the coverage, type 's' and press Enter
 *      to stop and print the final calibration values.
 *   5. Paste the printed #define lines into src/main.cpp.
 *   6. Re-flash the main firmware: pio run -t upload
 */

#include "HMC5883L.h"
#include <Arduino.h>
#include <Wire.h>

// ── Pin & address config (must match your main firmware) ──
#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2
#define HMC5883L_ADDR 0x1E

HMC5883L mag;

// ── Min / Max trackers ──
int16_t minX = 32767, maxX = -32768;
int16_t minY = 32767, maxY = -32768;
int16_t minZ = 32767, maxZ = -32768;

unsigned long sampleCount = 0;
bool running = true;

bool checkI2CDevice(uint8_t addr)
{
  Wire.beginTransmission(addr);
  return (Wire.endTransmission() == 0);
}

void printCalibration()
{
  Serial.println();
  Serial.println("╔══════════════════════════════════════════════════╗");
  Serial.println("║     MAGNETOMETER CALIBRATION RESULTS            ║");
  Serial.println("╚══════════════════════════════════════════════════╝");
  Serial.println();

  // Raw min/max
  Serial.printf("  X: min = %6d,  max = %6d\n", minX, maxX);
  Serial.printf("  Y: min = %6d,  max = %6d\n", minY, maxY);
  Serial.printf("  Z: min = %6d,  max = %6d\n", minZ, maxZ);
  Serial.println();

  // Hard-iron offsets (center of the min/max envelope)
  float offX = (maxX + minX) / 2.0f;
  float offY = (maxY + minY) / 2.0f;
  float offZ = (maxZ + minZ) / 2.0f;

  // Axis ranges
  float rangeX = (maxX - minX) / 2.0f;
  float rangeY = (maxY - minY) / 2.0f;
  float rangeZ = (maxZ - minZ) / 2.0f;

  // Soft-iron scale (normalize to average range)
  float avgRange = (rangeX + rangeY + rangeZ) / 3.0f;
  float scaleX = (rangeX > 0) ? avgRange / rangeX : 1.0f;
  float scaleY = (rangeY > 0) ? avgRange / rangeY : 1.0f;
  float scaleZ = (rangeZ > 0) ? avgRange / rangeZ : 1.0f;

  Serial.printf("  Samples collected: %lu\n", sampleCount);
  Serial.println();
  Serial.println("  ── Copy these lines into src/main.cpp ──");
  Serial.println();
  Serial.printf("  #define MAG_OFFSET_X %.1ff\n", offX);
  Serial.printf("  #define MAG_OFFSET_Y %.1ff\n", offY);
  Serial.printf("  #define MAG_OFFSET_Z %.1ff\n", offZ);
  Serial.printf("  #define MAG_SCALE_X  %.4ff\n", scaleX);
  Serial.printf("  #define MAG_SCALE_Y  %.4ff\n", scaleY);
  Serial.printf("  #define MAG_SCALE_Z  %.4ff\n", scaleZ);
  Serial.println();
  Serial.println("  ─────────────────────────────────────────");
  Serial.println();
}

void setup()
{
  Serial.begin(921600);
  delay(500);

  Serial.println();
  Serial.println("╔══════════════════════════════════════════════════╗");
  Serial.println("║     HMC5883L MAGNETOMETER CALIBRATION TOOL      ║");
  Serial.println("╚══════════════════════════════════════════════════╝");
  Serial.println();

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);

  if (!checkI2CDevice(HMC5883L_ADDR))
  {
    Serial.println("ERROR: HMC5883L not found at 0x1E!");
    Serial.println("Check wiring and I2C address. Halting.");
    while (true) { delay(1000); }
  }

  mag.initialize();
  Serial.println("HMC5883L: Connected and initialized.");
  Serial.println();
  Serial.println("Instructions:");
  Serial.println("  - Slowly rotate the sensor through ALL orientations.");
  Serial.println("  - Cover every angle: pitch, roll, yaw, and combinations.");
  Serial.println("  - Continue for at least 30 seconds.");
  Serial.println("  - Send 's' (then Enter) to stop and print results.");
  Serial.println();
  Serial.println("Collecting data...");
  Serial.println();
  Serial.println("   Sample |      X |      Y |      Z | minX  maxX | minY  maxY | minZ  maxZ");
  Serial.println("   -------+--------+--------+--------+------------+------------+-----------");
}

void loop()
{
  // Check for stop command
  if (Serial.available())
  {
    char c = Serial.read();
    if (c == 's' || c == 'S')
    {
      running = false;
      printCalibration();
      Serial.println("Calibration stopped. Reset or re-flash to run again.");
      while (true) { delay(1000); }
    }
  }

  if (!running) return;

  int16_t mx, my, mz;
  mag.getHeading(&mx, &my, &mz);

  // Update min/max
  if (mx < minX) minX = mx;
  if (mx > maxX) maxX = mx;
  if (my < minY) minY = my;
  if (my > maxY) maxY = my;
  if (mz < minZ) minZ = mz;
  if (mz > maxZ) maxZ = mz;

  sampleCount++;

  // Print every 20th sample (~5 Hz at 100Hz read rate) to avoid flooding
  if (sampleCount % 20 == 0)
  {
    Serial.printf("   %6lu | %6d | %6d | %6d | %5d %5d | %5d %5d | %5d %5d\n",
                  sampleCount, mx, my, mz,
                  minX, maxX, minY, maxY, minZ, maxZ);
  }

  delay(10); // ~100 Hz sampling
}
