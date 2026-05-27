"""
Gesture Control Module
Uses MediaPipe Hands to detect hand gestures and map them to EV commands.

Gesture → Command mapping:
  Open palm (all fingers up)  → "F" (Forward)
  Closed fist (all fingers down) → "S" (Stop)
  Hand tilted left             → "L" (Left)
  Hand tilted right            → "R" (Right)
  No hand detected             → "S" (Stop)
"""

import cv2
import mediapipe as mp
import numpy as np
import logging

logger = logging.getLogger(__name__)


class GestureController:
    def __init__(self):
        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils

        # Initialize MediaPipe Hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,          # Track one hand only
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6
        )

        self.current_gesture = "none"
        self.current_command = "S"

    def _count_fingers_up(self, landmarks) -> list:
        """
        Count which fingers are extended (up).
        Returns a list of booleans [thumb, index, middle, ring, pinky].
        """
        fingers = []

        # Landmark indices for fingertips and their lower joints
        # MediaPipe hand landmark IDs:
        # Thumb tip=4, IP=3 | Index tip=8, PIP=6 | Middle tip=12, PIP=10
        # Ring tip=16, PIP=14 | Pinky tip=20, PIP=18

        # Thumb: compare x position (horizontal) since thumb moves sideways
        if landmarks[4].x < landmarks[3].x:
            fingers.append(True)   # Thumb up (for right hand)
        else:
            fingers.append(False)

        # Four fingers: compare y position (tip above PIP joint = finger up)
        tip_ids = [8, 12, 16, 20]
        pip_ids = [6, 10, 14, 18]
        for tip, pip in zip(tip_ids, pip_ids):
            fingers.append(landmarks[tip].y < landmarks[pip].y)

        return fingers

    def _get_hand_tilt(self, landmarks) -> str:
        """
        Determine if hand is tilted left or right based on wrist vs middle finger base.
        Returns "left", "right", or "center".
        """
        wrist_x = landmarks[0].x
        middle_base_x = landmarks[9].x  # Middle finger MCP joint

        diff = middle_base_x - wrist_x

        if diff < -0.05:
            return "left"
        elif diff > 0.05:
            return "right"
        else:
            return "center"

    def detect_gesture(self, frame: np.ndarray) -> dict:
        """
        Process a video frame and detect hand gesture.
        
        Returns dict with:
          - gesture: string name of detected gesture
          - command: single char command (F/B/L/R/S)
          - hand_detected: bool
          - annotated_frame: frame with hand landmarks drawn
        """
        result = {
            "gesture": "none",
            "command": "S",
            "hand_detected": False,
            "annotated_frame": frame.copy()
        }

        # Convert BGR to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb_frame.flags.writeable = False
        detection = self.hands.process(rgb_frame)
        rgb_frame.flags.writeable = True

        if not detection.multi_hand_landmarks:
            result["gesture"] = "no_hand"
            result["command"] = "S"
            self.current_gesture = "no_hand"
            self.current_command = "S"
            return result

        result["hand_detected"] = True

        # Process first detected hand
        hand_landmarks = detection.multi_hand_landmarks[0]

        # Draw landmarks on frame
        self.mp_draw.draw_landmarks(
            result["annotated_frame"],
            hand_landmarks,
            self.mp_hands.HAND_CONNECTIONS
        )

        lm = hand_landmarks.landmark
        fingers_up = self._count_fingers_up(lm)
        tilt = self._get_hand_tilt(lm)
        fingers_count = sum(fingers_up)

        # --- Gesture Classification ---

        # Closed fist: all fingers down → STOP
        if fingers_count <= 1:
            gesture = "fist"
            command = "S"

        # Open palm: 4-5 fingers up → check tilt for direction
        elif fingers_count >= 4:
            if tilt == "left":
                gesture = "hand_left"
                command = "L"
            elif tilt == "right":
                gesture = "hand_right"
                command = "R"
            else:
                gesture = "open_palm"
                command = "F"

        # Partial fingers (2-3 up) → Stop as default
        else:
            gesture = "partial"
            command = "S"

        result["gesture"] = gesture
        result["command"] = command
        self.current_gesture = gesture
        self.current_command = command

        # Draw gesture label on frame
        cv2.putText(
            result["annotated_frame"],
            f"Gesture: {gesture} -> {command}",
            (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2
        )

        return result

    def release(self):
        """Release MediaPipe resources."""
        self.hands.close()
