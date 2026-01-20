#include <Arduino.h>
#include <Wire.h>

#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2
#define MPU_ADDR 0x68  // The address we found earlier

void setup() {
  Serial.begin(115200);
  while(!Serial);
  
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  delay(100);

  Serial.println("\n--- MPU Debugger & Force Reader ---");

  // 1. WAKE UP THE SENSOR
  // By default, the MPU starts in "Sleep Mode". We must write 0 to register 0x6B
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B); // PWR_MGMT_1 register
  Wire.write(0);    // Wake up!
  byte error = Wire.endTransmission();
  
  if (error != 0) {
    Serial.print("Error connecting to MPU. Error code: "); Serial.println(error);
    while(1);
  }

  // 2. CHECK "WHO AM I"
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x75); // WHO_AM_I register
  Wire.endTransmission();
  
  Wire.requestFrom(MPU_ADDR, 1);
  byte whoAmI = Wire.read();
  
  Serial.print("WHO_AM_I Register returns: 0x");
  Serial.println(whoAmI, HEX);
  
  if (whoAmI == 0x71) {
    Serial.println(" -> Valid MPU-9250!");
  } else if (whoAmI == 0x70) {
    Serial.println(" -> It is an MPU-6500 (6-axis only). The Magnetometer is missing.");
  } else {
    Serial.println(" -> Unknown or Fake chip.");
  }
  
  delay(1000);
}

void loop() {
  // 3. FORCE READ ACCELEROMETER
  // We read 6 bytes starting from register 0x3B (Accel X High Byte)
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission();
  
  Wire.requestFrom(MPU_ADDR, 6);
  
  if (Wire.available() == 6) {
    // Combine High and Low bytes
    int16_t accelX = (Wire.read() << 8) | Wire.read();
    int16_t accelY = (Wire.read() << 8) | Wire.read();
    int16_t accelZ = (Wire.read() << 8) | Wire.read();

    // Print raw values
    Serial.print("Raw Accel X: "); Serial.print(accelX);
    Serial.print(" | Y: "); Serial.print(accelY);
    Serial.print(" | Z: "); Serial.println(accelZ);
  }
  
  delay(200);
}