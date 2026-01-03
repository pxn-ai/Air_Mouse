#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_NeoPixel.h>
#include "USB.h"
#include "USBHIDMouse.h"

// --- Hardware Config ---
// CHECK YOUR PINOUT: S3 boards vary wildy!
// Common S3 DevKit: SDA=8, SCL=9, NeoPixel=48
// S3 Zero: SDA=5, SCL=6, NeoPixel=21
#define SDA_PIN 8
#define SCL_PIN 9
#define NEOPIXEL_PIN 48 

USBHIDMouse Mouse;
Adafruit_MPU6050 mpu;
Adafruit_NeoPixel pixels(1, NEOPIXEL_PIN, NEO_GRB + NEO_KHZ800);

// --- Mouse Tuning ---
const float GYRO_DEADZONE = 0.15;  // Rad/s
const float MOUSE_SENSITIVITY = 18.0; 
const float CLICK_THRESHOLD = 15.0; // Acceleration m/s^2 for shake click

// Timer for shake debounce
unsigned long lastClickTime = 0;

void setup() {
    // Start Native USB
    USB.begin();
    Mouse.begin();
    Serial.begin(115200);

    // Init NeoPixel
    pixels.begin();
    pixels.setBrightness(30);
    pixels.setPixelColor(0, pixels.Color(255, 100, 0)); // Orange = Booting
    pixels.show();

    // Init I2C
    Wire.begin(SDA_PIN, SCL_PIN);

    // Init MPU6050
    if (!mpu.begin()) {
        Serial.println("MPU6050 Not Found!");
        while (1) {
            pixels.setPixelColor(0, pixels.Color(255, 0, 0)); // Red = Error
            pixels.show();
            delay(100);
            pixels.setPixelColor(0, 0);
            pixels.show();
            delay(100);
        }
    }

    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);

    pixels.setPixelColor(0, pixels.Color(0, 255, 0)); // Green = Ready
    pixels.show();
}

void loop() {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);

    // --- 1. Mouse Movement (Gyro) ---
    // MPU6050 Orientation mapping - Change signs/axes based on how you hold it
    float gyroZ = g.gyro.z; // Yaw (Left/Right)
    float gyroY = g.gyro.y; // Pitch (Up/Down)

    int moveX = 0;
    int moveY = 0;

    if (abs(gyroZ) > GYRO_DEADZONE) {
        moveX = (int)(gyroZ * MOUSE_SENSITIVITY * -1);
    }
    if (abs(gyroY) > GYRO_DEADZONE) {
        moveY = (int)(gyroY * MOUSE_SENSITIVITY * -1);
    }

    if (moveX != 0 || moveY != 0) {
        Mouse.move(moveX, moveY);
    }

    // --- 2. Shake to Click (Accelerometer) ---
    // If total acceleration vector is high, it's a shake
    // Gravity is ~9.8, so we look for spikes well above that
    float totalAccel = sqrt(pow(a.acceleration.x, 2) + 
                            pow(a.acceleration.y, 2) + 
                            pow(a.acceleration.z, 2));

    if (totalAccel > CLICK_THRESHOLD && millis() - lastClickTime > 500) {
        Mouse.click(MOUSE_LEFT);
        lastClickTime = millis();
        
        // Visual Feedback for Click (White Flash)
        pixels.setPixelColor(0, pixels.Color(255, 255, 255));
        pixels.show();
        delay(50); 
        pixels.setPixelColor(0, pixels.Color(0, 255, 0));
        pixels.show();
    }
}