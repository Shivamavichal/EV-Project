"""
Camera Stream Module
Manages webcam capture, runs face recognition and gesture detection,
and provides MJPEG stream for the Flask dashboard.
"""

import cv2
import numpy as np
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class CameraStream:
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[np.ndarray] = None
        self.is_running = False
        self._lock = threading.Lock()

        # AI module references (set externally)
        self.face_recognizer = None
        self.gesture_controller = None

        # State shared with Flask app
        self.state = {
            "authorized": False,
            "face_detected": False,
            "face_confidence": 999.0,
            "matched_user": "",
            "gesture": "none",
            "command": "S",
            "hand_detected": False,
            "last_gesture_time": time.time(),
            "frame_count": 0
        }

        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Open webcam and start background capture thread."""
        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            logger.error(f"Cannot open camera index {self.camera_index}")
            return False

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info(f"Camera started on index {self.camera_index}")
        return True

    def stop(self):
        """Stop capture and release camera."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.cap:
            self.cap.release()
        logger.info("Camera stopped.")

    def _capture_loop(self):
        """Background thread: capture frames and run AI processing."""
        while self.is_running:
            ret, frame = self.cap.read()
            if not ret:
                logger.warning("Failed to read frame from camera.")
                time.sleep(0.1)
                continue

            # Flip frame horizontally (mirror effect - more natural for gestures)
            frame = cv2.flip(frame, 1)

            processed = frame.copy()

            # --- Face Recognition ---
            if self.face_recognizer:
                face_result = self.face_recognizer.recognize(frame)
                with self._lock:
                    self.state["authorized"]     = face_result["authorized"]
                    self.state["face_detected"]  = face_result["face_detected"]
                    self.state["face_confidence"] = face_result["confidence"]
                    self.state["matched_user"]   = face_result.get("matched_user", "")
                processed = face_result["annotated_frame"]

            # --- Gesture Detection (only if authorized) ---
            if self.gesture_controller and self.state.get("authorized", False):
                gesture_result = self.gesture_controller.detect_gesture(processed)
                with self._lock:
                    self.state["gesture"] = gesture_result["gesture"]
                    self.state["command"] = gesture_result["command"]
                    self.state["hand_detected"] = gesture_result["hand_detected"]
                    if gesture_result["hand_detected"]:
                        self.state["last_gesture_time"] = time.time()
                processed = gesture_result["annotated_frame"]
            else:
                with self._lock:
                    self.state["gesture"] = "locked"
                    self.state["command"] = "S"
                    self.state["hand_detected"] = False

            # Draw status overlay on frame
            self._draw_status_overlay(processed)

            with self._lock:
                self.current_frame = processed
                self.state["frame_count"] += 1

    def _draw_status_overlay(self, frame: np.ndarray):
        """Draw status text overlay on the video frame."""
        authorized = self.state.get("authorized", False)
        status_text = "UNLOCKED" if authorized else "LOCKED"
        status_color = (0, 255, 0) if authorized else (0, 0, 255)

        # Background bar at top
        cv2.rectangle(frame, (0, 0), (640, 35), (0, 0, 0), -1)
        cv2.putText(frame, f"EV Status: {status_text}", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

        cmd = self.state.get("command", "S")
        cv2.putText(frame, f"CMD: {cmd}", (500, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    def get_frame(self) -> Optional[np.ndarray]:
        """Get the latest processed frame (thread-safe)."""
        with self._lock:
            return self.current_frame.copy() if self.current_frame is not None else None

    def get_state(self) -> dict:
        """Get current AI state (thread-safe)."""
        with self._lock:
            return self.state.copy()

    def generate_mjpeg(self):
        """Generator for MJPEG streaming to Flask."""
        while True:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.05)
                continue

            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                continue

            yield (
                b'--frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' +
                buffer.tobytes() +
                b'\r\n'
            )
            time.sleep(0.033)  # ~30 FPS
