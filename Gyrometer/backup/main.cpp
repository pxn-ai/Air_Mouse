#include <Arduino.h>
#include <Wire.h>
#include <MPU9250_WE.h>
#include <QMC5883LCompass.h>

#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2

MPU6500_WE myMPU6500 = MPU6500_WE(0x68);
QMC5883LCompass myMag;

void setup()
{
  Serial.begin(115200);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  delay(100);

  // Initialize MPU-6500
  if (!myMPU6500.init())
  {
    Serial.println("MPU-6500 not found!");
    while (1)
      ;
  }

  // Initialize Magnetometer
  myMag.init();

  Serial.println("9-Axis Fusion System Online...");
  Serial.println("Keep sensor flat for calibration...");
  delay(1000);
  myMPU6500.autoOffsets();
  
  myMPU6500.init();
  myMag.init();
  
  // REPLACE THESE NUMBERS with the ones you found in the step above
  // Format: setCalibration(minX, maxX, minY, maxY, minZ, maxZ);
  myMag.setCalibration(0, 0, 0, 0, 0, 0); 
  
  Serial.println("9-Axis Fusion Ready!");
}

void loop()
{
  // 1. Get Orientation from Accel/Gyro
  float pitch = myMPU6500.getPitch();
  float roll = myMPU6500.getRoll();

  // 2. Get Compass Data
  myMag.read();
  int azimuth = myMag.getAzimuth(); // Returns heading in degrees (0-360)

  // 3. Display Integrated Data
  Serial.print("Orientation -> Pitch: ");
  Serial.print(pitch);
  Serial.print(" | Roll: ");
  Serial.print(roll);
  Serial.print(" | Heading (Yaw): ");
  Serial.print(azimuth);

  // Cardinal Direction helper
  char direction[3];
  myMag.getDirection(direction, azimuth);
  Serial.print(" [");
  Serial.print(direction);
  Serial.println("]");

  delay(100);
}