/*
  AI Smart EV Security and Parking Assistance System
  ESP32 Firmware

  Hardware:
    - ESP32 Dev Board
    - L298N Motor Driver
    - 2x DC Motors (or 4-wheel chassis)
    - HC-SR04 Ultrasonic Sensor
    - Optional: LED + Buzzer

  Wiring:
    ESP32 -> L298N:
      GPIO 27 -> IN1
      GPIO 26 -> IN2
      GPIO 25 -> IN3
      GPIO 33 -> IN4
      GPIO 14 -> ENA (PWM speed control - Motor A)
      GPIO 32 -> ENB (PWM speed control - Motor B)

    ESP32 -> HC-SR04:
      GPIO 5  -> TRIG
      GPIO 18 -> ECHO
      3.3V    -> VCC  (use 5V if sensor requires it via separate supply)
      GND     -> GND

    Optional:
      GPIO 2  -> LED (onboard LED)
      GPIO 4  -> Buzzer

    IMPORTANT: Common GND between ESP32, L298N, and battery pack!
*/

// ===================== PIN DEFINITIONS =====================

// L298N Motor Driver pins
#define IN1  27   // Motor A direction pin 1
#define IN2  26   // Motor A direction pin 2
#define IN3  25   // Motor B direction pin 1
#define IN4  33   // Motor B direction pin 2
#define ENA  14   // Motor A enable (PWM)
#define ENB  32   // Motor B enable (PWM)

// HC-SR04 Ultrasonic Sensor pins
#define TRIG_PIN  5
#define ECHO_PIN  18

// Optional LED and Buzzer
#define LED_PIN    2   // Onboard LED
#define BUZZER_PIN 4   // Buzzer (set to -1 if not used)

// ===================== CONSTANTS =====================

#define MOTOR_SPEED       200   // PWM speed 0-255
#define TURN_SPEED        180   // Slightly slower for turns
#define OBSTACLE_LIMIT_CM 10    // Stop if obstacle closer than this
#define SERIAL_BAUD       115200
#define DISTANCE_INTERVAL 200   // Send distance every 200ms

// ===================== GLOBAL VARIABLES =====================

char currentCommand = 'S';       // Current movement command
float lastDistance = 999.0;      // Last measured distance in cm
bool obstacleDetected = false;   // Obstacle flag
unsigned long lastDistanceTime = 0;

// ===================== SETUP =====================

void setup() {
  Serial.begin(SERIAL_BAUD);

  // Motor driver pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);
  pinMode(ENA, OUTPUT);
  pinMode(ENB, OUTPUT);

  // Ultrasonic sensor pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Optional LED and buzzer
  pinMode(LED_PIN, OUTPUT);
  if (BUZZER_PIN >= 0) {
    pinMode(BUZZER_PIN, OUTPUT);
  }

  // Start with motors stopped
  stopMotors();

  // Startup signal: blink LED 3 times
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(200);
    digitalWrite(LED_PIN, LOW);
    delay(200);
  }

  Serial.println("ESP32 Smart EV Ready");
}

// ===================== MAIN LOOP =====================

void loop() {
  // Read command from Python via serial
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    // Only process valid commands
    if (cmd == 'F' || cmd == 'B' || cmd == 'L' || cmd == 'R' || cmd == 'S') {
      currentCommand = cmd;
    }
  }

  // Measure distance periodically
  if (millis() - lastDistanceTime >= DISTANCE_INTERVAL) {
    lastDistance = measureDistance();
    obstacleDetected = (lastDistance > 0 && lastDistance < OBSTACLE_LIMIT_CM);
    lastDistanceTime = millis();

    // Send distance data back to Python
    Serial.print("DIST:");
    Serial.println(lastDistance);

    // Send obstacle status
    Serial.print("OBSTACLE:");
    Serial.println(obstacleDetected ? 1 : 0);
  }

  // Safety: if obstacle detected, override command to Stop
  if (obstacleDetected) {
    stopMotors();
    warningSignal();
  } else {
    // Execute the received command
    executeCommand(currentCommand);
  }
}

// ===================== MOTOR CONTROL =====================

void moveForward() {
  analogWrite(ENA, MOTOR_SPEED);
  analogWrite(ENB, MOTOR_SPEED);
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void moveBackward() {
  analogWrite(ENA, MOTOR_SPEED);
  analogWrite(ENB, MOTOR_SPEED);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void turnLeft() {
  // Left motor backward, right motor forward
  analogWrite(ENA, TURN_SPEED);
  analogWrite(ENB, TURN_SPEED);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, HIGH);
  digitalWrite(IN3, HIGH);
  digitalWrite(IN4, LOW);
}

void turnRight() {
  // Left motor forward, right motor backward
  analogWrite(ENA, TURN_SPEED);
  analogWrite(ENB, TURN_SPEED);
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}

void stopMotors() {
  analogWrite(ENA, 0);
  analogWrite(ENB, 0);
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void executeCommand(char cmd) {
  switch (cmd) {
    case 'F': moveForward();  break;
    case 'B': moveBackward(); break;
    case 'L': turnLeft();     break;
    case 'R': turnRight();    break;
    case 'S': stopMotors();   break;
    default:  stopMotors();   break;
  }
}

// ===================== ULTRASONIC SENSOR =====================

float measureDistance() {
  // Send 10us pulse to TRIG
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  // Measure ECHO pulse duration (timeout = 30ms = ~5 meters max)
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);

  if (duration == 0) {
    return 999.0;  // No echo received = no obstacle in range
  }

  // Convert to cm: speed of sound = 343 m/s = 0.0343 cm/us
  // Distance = (duration / 2) * 0.0343
  float distance = (duration / 2.0) * 0.0343;
  return distance;
}

// ===================== WARNING SIGNAL =====================

void warningSignal() {
  // Flash LED when obstacle detected
  digitalWrite(LED_PIN, (millis() / 200) % 2);  // Blink at 5Hz

  // Buzzer beep if connected
  if (BUZZER_PIN >= 0) {
    int beepState = (millis() / 300) % 2;
    digitalWrite(BUZZER_PIN, beepState);
  }
}
