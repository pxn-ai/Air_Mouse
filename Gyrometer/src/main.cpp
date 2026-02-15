#include "HMC5883L.h"
#include <Arduino.h>
#include <MPU9250_WE.h>
#include <MadgwickAHRS.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Wire.h>

// ╔══════════════════════════════════════════════════╗
// ║         USER CONFIGURATION — EDIT HERE          ║
// ╚══════════════════════════════════════════════════╝
#define WIFI_SSID "TP-LINK_85596C"
#define WIFI_PASS "Pasan745"

// ESP32 Static IP (must match your current WiFi network subnet)
#define STATIC_IP 192, 168, 1, 50
#define GATEWAY 192, 168, 1, 1
#define SUBNET 255, 255, 255, 0

// Server (your Mac) — where UDP packets are sent
#define SERVER_IP 192, 168, 1, 100
#define UDP_PORT 4210

// ╔══════════════════════════════════════════════════╗
// ║             HARDWARE CONFIGURATION              ║
// ╚══════════════════════════════════════════════════╝
#define I2C_SDA_PIN 1
#define I2C_SCL_PIN 2
// Correct addresses
#define MPU6500_ADDR 0x68
#define HMC5883L_ADDR 0x1E

// ── HMC5883L Calibration (Placeholders) ──
#define MAG_OFFSET_X 0.0f
#define MAG_OFFSET_Y 0.0f
#define MAG_OFFSET_Z 0.0f
#define MAG_SCALE_X 1.0f
#define MAG_SCALE_Y 1.0f
#define MAG_SCALE_Z 1.0f
#define MAG_UT_PER_LSB (100.0f / 1090.0f)

// ── Objects ──
MPU6500_WE imu = MPU6500_WE(MPU6500_ADDR); // MPU6500, NOT MPU9250!
HMC5883L mag;
Madgwick filter;
WiFiUDP udp;

// ── Timing ──
unsigned long lastUpdate = 0;
unsigned long lastStatusCheck = 0;
unsigned long lastWiFiCheck = 0;
unsigned long lastDiag = 0;

// ── State ──
bool imuConnected = true;
bool magConnected = true;
bool useWiFi = false;
bool wifiEverConnected = false;

// ── EMA smoothing ──
const float EMA_ALPHA = 0.15f; // lower = smoother but more lag
float smoothRoll = 0, smoothPitch = 0, smoothYaw = 0;
bool emaInitialized = false;

// Static IP objects
IPAddress staticIP(STATIC_IP);
IPAddress gateway(GATEWAY);
IPAddress subnet(SUBNET);
IPAddress serverIP(SERVER_IP);

// ── I2C health check ──
bool checkI2CDevice(uint8_t addr) {
  Wire.beginTransmission(addr);
  return (Wire.endTransmission() == 0);
}

// ── Send a line over the active transport ──
void sendLine(const String &line) {
  if (useWiFi) {
    udp.beginPacket(serverIP, UDP_PORT);
    udp.print(line);
    udp.endPacket();
  } else {
    Serial.println(line);
    Serial.flush(); // Ensure the entire line is transmitted before anything
                    // else prints
  }
}

// ── Angle-aware EMA (handles wraparound) ──
float emaAngle(float smoothed, float raw, float alpha) {
  float diff = raw - smoothed;
  // Wrap the difference to [-180, 180]
  while (diff > 180.0f)
    diff -= 360.0f;
  while (diff < -180.0f)
    diff += 360.0f;
  return smoothed + alpha * diff;
}

// ── WiFi setup with timeout ──
bool setupWiFi() {
  Serial.print("WiFi: Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  // IP Config restored!
  WiFi.config(staticIP, gateway, subnet);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 5000) {
    delay(100);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi: Connected! IP = ");
    Serial.println(WiFi.localIP());
    Serial.print("WiFi: Gateway: ");
    Serial.println(WiFi.gatewayIP());
    Serial.print("WiFi: Sending UDP to ");
    Serial.print(serverIP);
    Serial.print(":");
    Serial.println(UDP_PORT);

    wifiEverConnected = true;
    return true;
  } else {
    Serial.println("WiFi: FAILED — falling back to Serial");
    Serial.println("WIFI_FAIL");
    WiFi.disconnect(true);
    return false;
  }
}

void setup() {
  Serial.begin(921600);
  delay(500);

  Serial.println("=== ESP32 Hardware Check ===");
  Serial.printf("Flash size: %d MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.println("============================");

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000);

  // Check devices
  imuConnected = checkI2CDevice(MPU6500_ADDR);
  magConnected = checkI2CDevice(HMC5883L_ADDR);

  if (!imuConnected)
    Serial.println("ERROR: MPU6500 not found!");
  if (!magConnected)
    Serial.println("ERROR: HMC5883L not found!");

  if (imuConnected) {
    if (!imu.init()) {
      Serial.println("ERROR: MPU6500 init failed!");
      imuConnected = false;
    } else {
      Serial.println("MPU6500: Calibrating...");
      imu.autoOffsets();
      Serial.println("MPU6500: Done.");
      imu.enableGyrDLPF();
      imu.setGyrDLPF(MPU6500_DLPF_6);
      imu.enableAccDLPF(true);
      imu.setAccDLPF(MPU6500_DLPF_6);
      imu.setSampleRateDivider(9); // 1kHz / (1+9) = 100Hz
      imu.setAccRange(MPU6500_ACC_RANGE_4G);
      imu.setGyrRange(MPU6500_GYRO_RANGE_500);
    }
  }

  if (magConnected) {
    mag.initialize();
    Serial.println("HMC5883L: Initialized.");
  }

  filter.begin(100);

  // Attempt WiFi
  useWiFi = setupWiFi();

  // Send transport mode once via the active channel
  sendLine(String("TRANSPORT,") + (useWiFi ? "wifi" : "serial"));
}

void loop() {
  // ── WiFi watchdog ──
  if (millis() - lastWiFiCheck >= 2000) {
    lastWiFiCheck = millis();

    if (useWiFi && WiFi.status() != WL_CONNECTED) {
      useWiFi = false;
      sendLine("TRANSPORT,serial");
    } else if (!useWiFi && wifiEverConnected) {
      if (WiFi.status() == WL_CONNECTED) {
        useWiFi = true;
        sendLine("TRANSPORT,wifi");
      } else {
        WiFi.begin(WIFI_SSID, WIFI_PASS);
      }
    }
  }

  // ── I2C health ──
  if (millis() - lastStatusCheck >= 500) {
    lastStatusCheck = millis();
    imuConnected = checkI2CDevice(MPU6500_ADDR);
    magConnected = checkI2CDevice(HMC5883L_ADDR);
    String status = "STATUS," + String(imuConnected ? 1 : 0) + "," +
                    String(magConnected ? 1 : 0);
    sendLine(status);
  }

  // ── Sensor read ──
  if (millis() - lastUpdate >= 10) {
    lastUpdate = millis();

    if (imuConnected) {
      xyzFloat a = imu.getGValues();
      xyzFloat g = imu.getGyrValues();

      float mx_ut = 0, my_ut = 0, mz_ut = 0;
      bool magValid = false;
      if (magConnected) {
        int16_t mx_raw = 0, my_raw = 0, mz_raw = 0;
        mag.getHeading(&mx_raw, &my_raw, &mz_raw);
        mx_ut = (mx_raw - MAG_OFFSET_X) * MAG_SCALE_X * MAG_UT_PER_LSB;
        my_ut = (my_raw - MAG_OFFSET_Y) * MAG_SCALE_Y * MAG_UT_PER_LSB;
        mz_ut = (mz_raw - MAG_OFFSET_Z) * MAG_SCALE_Z * MAG_UT_PER_LSB;
        // Only valid if not all zeros (would cause div-by-zero in Madgwick)
        magValid = (mx_raw != 0 || my_raw != 0 || mz_raw != 0);
      }

      // Use 9-axis update only if mag data is valid, otherwise 6-axis
      if (magValid) {
        filter.update(g.x, g.y, g.z, a.x, a.y, a.z, mx_ut, my_ut, mz_ut);
      } else {
        filter.updateIMU(g.x, g.y, g.z, a.x, a.y, a.z);
      }

      float roll = filter.getRoll();
      float pitch = filter.getPitch();
      float yaw = filter.getYaw();

      // Guard against nan (can happen during first few iterations)
      if (!isnan(roll) && !isnan(pitch) && !isnan(yaw)) {
        // Apply EMA smoothing
        if (!emaInitialized) {
          smoothRoll = roll;
          smoothPitch = pitch;
          smoothYaw = yaw;
          emaInitialized = true;
        } else {
          smoothRoll = emaAngle(smoothRoll, roll, EMA_ALPHA);
          smoothPitch = emaAngle(smoothPitch, pitch, EMA_ALPHA);
          smoothYaw = emaAngle(smoothYaw, yaw, EMA_ALPHA);
        }

        String euler = "EULER," + String(smoothRoll, 2) + "," +
                       String(smoothPitch, 2) + "," + String(smoothYaw, 2);
        sendLine(euler);
      }

      // Periodic diagnostic (every 3 seconds)
      if (millis() - lastDiag >= 3000) {
        lastDiag = millis();
        Serial.printf("DIAG: a=(%.2f,%.2f,%.2f) g=(%.1f,%.1f,%.1f) "
                      "m=(%.1f,%.1f,%.1f) magValid=%d RPY=(%.1f,%.1f,%.1f)\n",
                      a.x, a.y, a.z, g.x, g.y, g.z, mx_ut, my_ut, mz_ut,
                      magValid, roll, pitch, yaw);
      }
    }
  }
}