#include <Arduino.h>
#include <Wire.h>
#include <MPU6500_WE.h>

#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2

// Setup for MPU6500 at address 0x68
MPU6500_WE myMPU = MPU6500_WE(0x68);

void setup() {
  Serial.begin(115200);
  // Remove the "while(!Serial)" line so the board starts even without the monitor open
  
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  delay(100);

  Serial.println("Initializing MPU-6500...");
  
  // Initialize the sensor
  if(!myMPU.init()){
    Serial.println("MPU6500 does not respond!");
    Serial.println("Check wiring (SDA/SCL) and address.");
    while(1);
  }
  Serial.println("MPU-6500 connected!");

  // --- CALIBRATION ---
  Serial.println("Position sensor flat and do not move it!");
  delay(1000);
  
  Serial.println("Calibrating...");
  myMPU.autoOffsets(); // Auto-calibrates gyro and accel
  Serial.println("Done!");
  
  // Optional: Set filters to smooth out the data
  myMPU.setAccRange(MPU6500_ACC_RANGE_2G);
  myMPU.setGyrRange(MPU6500_GYRO_RANGE_250);
}

void loop() {
  // 1. Get raw G-force and Gyro data
  xyzFloat gValue = myMPU.getGValues();
  xyzFloat gyr = myMPU.getGyrValues();
  
  // 2. Get Calculated Angles (Pitch and Roll)
  // This library does the math for you!
  float pitch = myMPU.getPitch();
  float roll  = myMPU.getRoll();

  // 3. Print Data
  Serial.print("Pitch: "); Serial.print(pitch);
  Serial.print("  | Roll: "); Serial.print(roll);
  
  Serial.print("    (Accel Z: "); Serial.print(gValue.z); // Should be ~1.0 when flat
  Serial.println(")");

  delay(100);
}