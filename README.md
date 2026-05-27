# AI Smart EV Security and Parking Assistance System

Control a physical ESP32-based EV model using face recognition and hand gestures via a Python + Flask web dashboard.

---

## System Flow

```
Laptop Webcam → Python AI → Flask Backend → USB Serial → ESP32 → L298N → DC Motors
```

---

## Hardware Required

| Component         | Quantity |
|-------------------|----------|
| ESP32 Dev Board   | 1        |
| L298N Motor Driver| 1        |
| DC Motors         | 2–4      |
| HC-SR04 Ultrasonic| 1        |
| Battery Pack (7–12V) | 1     |
| LED (optional)    | 1        |
| Buzzer (optional) | 1        |
| Jumper wires      | —        |

---

## Wiring Guide

### ESP32 → L298N Motor Driver

| ESP32 GPIO | L298N Pin | Purpose              |
|------------|-----------|----------------------|
| GPIO 27    | IN1       | Motor A direction 1  |
| GPIO 26    | IN2       | Motor A direction 2  |
| GPIO 25    | IN3       | Motor B direction 1  |
| GPIO 33    | IN4       | Motor B direction 2  |
| GPIO 14    | ENA       | Motor A speed (PWM)  |
| GPIO 32    | ENB       | Motor B speed (PWM)  |
| GND        | GND       | Common ground        |

### ESP32 → HC-SR04 Ultrasonic Sensor

| ESP32 GPIO | HC-SR04 Pin | Purpose       |
|------------|-------------|---------------|
| GPIO 5     | TRIG        | Trigger pulse |
| GPIO 18    | ECHO        | Echo return   |
| 3.3V / 5V  | VCC         | Power         |
| GND        | GND         | Ground        |

### Optional

| ESP32 GPIO | Component | Purpose        |
|------------|-----------|----------------|
| GPIO 2     | LED       | Obstacle warning|
| GPIO 4     | Buzzer    | Obstacle beep  |

> **IMPORTANT:** Connect GND of ESP32, L298N, and battery pack together (common ground).
> L298N motor power (12V terminal) connects to your battery pack.
> L298N 5V output can power ESP32 if jumper is set correctly.

---

## Installation

### 1. Install Python dependencies

```bash
cd smart_ev_project
pip install -r requirements.txt
```

> Python 3.9+ recommended.

### 2. Add your face photo

Place a clear, frontal face photo of the authorized owner at:
```
known_faces/owner.jpg
```
The face must be clearly visible, well-lit, and facing the camera.

### 3. Configure the system

Edit `config.json`:

```json
{
  "serial_port": "COM3",        // Windows: COM3, COM4 etc. | Linux: /dev/ttyUSB0
  "baud_rate": 115200,
  "simulation_mode": false,     // Set true to test without ESP32
  "authorized_face_path": "known_faces/owner.jpg",
  "obstacle_distance_limit": 10,
  "camera_index": 0,            // 0 = default webcam
  "gesture_timeout_seconds": 2,
  "flask_host": "0.0.0.0",
  "flask_port": 5000
}
```

### 4. Upload ESP32 code

1. Open Arduino IDE (2.x recommended)
2. Install ESP32 board support:
   - Go to File → Preferences → Additional Board URLs
   - Add: `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
   - Go to Tools → Board Manager → search "esp32" → Install
3. Open `hardware/esp32_smart_ev.ino`
4. Select board: **ESP32 Dev Module**
5. Select the correct COM port
6. Click Upload

### 5. Find your COM port

**Windows:**
- Open Device Manager → Ports (COM & LPT)
- Look for "Silicon Labs CP210x" or "CH340" → note the COM number

**Linux/Mac:**
```bash
ls /dev/ttyUSB*
# or
ls /dev/ttyACM*
```

### 6. Run the Flask app

```bash
cd smart_ev_project
python app.py
```

### 7. Open the dashboard

Open your browser and go to:
```
http://localhost:5000
```

---

## Testing Without ESP32 (Simulation Mode)

Set `simulation_mode: true` in `config.json`. The system will:
- Skip real serial connection
- Simulate distance sensor data
- Log all commands to console
- Dashboard works fully

---

## Gesture Controls

| Gesture         | Command | Action   |
|-----------------|---------|----------|
| Open palm       | F       | Forward  |
| Tilt hand left  | L       | Left     |
| Tilt hand right | R       | Right    |
| Closed fist     | S       | Stop     |
| No hand visible | S       | Stop     |

---

## Keyboard Shortcuts (Dashboard)

| Key         | Action   |
|-------------|----------|
| Arrow Up    | Forward  |
| Arrow Down  | Backward |
| Arrow Left  | Left     |
| Arrow Right | Right    |
| Spacebar    | Stop     |

---

## Safety Rules

- Vehicle will not move until authorized face is detected
- If obstacle is closer than 10 cm, motors stop automatically
- If no gesture detected for 2 seconds, Stop command is sent
- Emergency Stop button always works regardless of lock state
- Serial disconnect warning shown on dashboard

---

## Project Structure

```
smart_ev_project/
├── app.py                        # Flask backend + main entry point
├── config.json                   # All configuration settings
├── requirements.txt              # Python dependencies
├── ai/
│   ├── face_recognition_cv.py   # OpenCV LBPH face recognition
│   ├── gesture_control.py       # MediaPipe hand gesture detection
│   └── camera_stream.py         # Webcam capture + MJPEG stream
├── hardware/
│   ├── serial_comm.py           # PySerial ESP32 communication
│   └── esp32_smart_ev.ino       # Arduino code for ESP32
├── templates/
│   └── index.html               # Dashboard HTML
├── static/
│   ├── style.css                # Dashboard styles
│   └── script.js                # Dashboard JavaScript
├── known_faces/
│   └── owner.jpg                # Authorized face photo (add yours)
└── logs/
    └── system_logs.txt          # Runtime logs
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Camera not opening | Change `camera_index` in config.json (try 1 or 2) |
| Face not recognized | Retake owner.jpg in good lighting, click "Reload Face Model" |
| ESP32 not connecting | Check COM port in config.json, ensure correct drivers installed |
| Motors not moving | Check L298N wiring, ensure common GND, check battery voltage |
| Obstacle always triggered | Check HC-SR04 wiring, ensure ECHO/TRIG not swapped |
| mediapipe install fails | Use Python 3.9–3.11, avoid 3.12+ |
