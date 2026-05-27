"""
Serial Communication Module
Handles USB serial connection to ESP32.
Supports real hardware mode and simulation mode.
"""

import serial
import serial.tools.list_ports
import threading
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SerialComm:
    def __init__(self, port: str, baud_rate: int = 115200, simulation_mode: bool = False):
        """
        :param port: COM port string e.g. "COM3" or "/dev/ttyUSB0"
        :param baud_rate: Serial baud rate (must match ESP32 code)
        :param simulation_mode: If True, skip real serial and just log commands
        """
        self.port = port
        self.baud_rate = baud_rate
        self.simulation_mode = simulation_mode

        self.serial_conn: Optional[serial.Serial] = None
        self.is_connected = False
        self.last_command = "S"
        self.last_distance = 0.0
        self.obstacle_detected = False

        self._lock = threading.Lock()
        self._read_thread: Optional[threading.Thread] = None
        self._running = False

        # Simulated distance for simulation mode
        self._sim_distance = 50.0

    def connect(self) -> bool:
        """Attempt to connect to ESP32 via serial port."""
        if self.simulation_mode:
            self.is_connected = True
            logger.info("SIMULATION MODE: Serial connection simulated.")
            self._running = True
            self._read_thread = threading.Thread(target=self._sim_read_loop, daemon=True)
            self._read_thread.start()
            return True

        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=1
            )
            time.sleep(2)  # Wait for ESP32 to reset after serial connect
            self.is_connected = True
            self._running = True

            # Start background thread to read data from ESP32
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()

            logger.info(f"Connected to ESP32 on {self.port} at {self.baud_rate} baud.")
            return True

        except serial.SerialException as e:
            logger.error(f"Failed to connect to {self.port}: {e}")
            self.is_connected = False
            return False

    def disconnect(self):
        """Close serial connection."""
        self._running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        self.is_connected = False
        logger.info("Serial connection closed.")

    def send_command(self, command: str) -> bool:
        """
        Send a single-character command to ESP32.
        Valid commands: F (forward), B (backward), L (left), R (right), S (stop)
        """
        valid_commands = {"F", "B", "L", "R", "S"}
        if command not in valid_commands:
            logger.warning(f"Invalid command: {command}")
            return False

        with self._lock:
            self.last_command = command

        if self.simulation_mode:
            logger.info(f"[SIM] Command sent: {command}")
            return True

        if not self.is_connected or not self.serial_conn:
            logger.warning("Cannot send command: not connected.")
            return False

        try:
            self.serial_conn.write(command.encode())
            self.serial_conn.flush()
            logger.debug(f"Sent command: {command}")
            return True
        except serial.SerialException as e:
            logger.error(f"Serial write error: {e}")
            self.is_connected = False
            return False

    def _read_loop(self):
        """Background thread: read data from ESP32 (distance, obstacle status)."""
        while self._running and self.is_connected:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode("utf-8", errors="ignore").strip()
                    self._parse_esp32_data(line)
            except serial.SerialException as e:
                logger.error(f"Serial read error: {e}")
                self.is_connected = False
                break
            except Exception as e:
                logger.warning(f"Read loop error: {e}")
            time.sleep(0.05)

    def _sim_read_loop(self):
        """Simulation mode: generate fake distance data."""
        while self._running:
            # Simulate varying distance
            import math
            t = time.time()
            self._sim_distance = 30 + 20 * math.sin(t * 0.5)
            with self._lock:
                self.last_distance = self._sim_distance
                self.obstacle_detected = self._sim_distance < 10
            time.sleep(0.5)

    def _parse_esp32_data(self, line: str):
        """
        Parse data sent from ESP32.
        Expected format: "DIST:25.3" or "OBSTACLE:1" or "OBSTACLE:0"
        """
        try:
            if line.startswith("DIST:"):
                distance = float(line.split(":")[1])
                with self._lock:
                    self.last_distance = distance
                    self.obstacle_detected = distance < 10
                logger.debug(f"Distance: {distance} cm")

            elif line.startswith("OBSTACLE:"):
                status = int(line.split(":")[1])
                with self._lock:
                    self.obstacle_detected = bool(status)

        except (ValueError, IndexError) as e:
            logger.debug(f"Could not parse ESP32 data '{line}': {e}")

    def get_status(self) -> dict:
        """Return current connection and sensor status."""
        with self._lock:
            return {
                "connected": self.is_connected,
                "simulation_mode": self.simulation_mode,
                "port": self.port,
                "last_command": self.last_command,
                "distance_cm": round(self.last_distance, 1),
                "obstacle_detected": self.obstacle_detected
            }

    @staticmethod
    def list_available_ports() -> list:
        """List all available serial ports on the system."""
        ports = serial.tools.list_ports.comports()
        return [p.device for p in ports]
