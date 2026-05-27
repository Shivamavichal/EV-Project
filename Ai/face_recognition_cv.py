"""
Face Recognition Module
Uses OpenCV LBPH face recognizer.
Supports multiple face images per user (up to 2).
Trained dynamically per logged-in user session.
"""

import cv2
import numpy as np
import os
import logging

logger = logging.getLogger(__name__)

LBPH_CONFIDENCE_LIMIT = 80   # Lower = stricter match


class FaceRecognizer:
    def __init__(self):
        # Haar Cascade face detector (built into OpenCV)
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)

        # LBPH recognizer instance
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.is_trained = False
        self.current_user: str = ""

    def train_for_user(self, face_paths: list[str], username: str):
        """
        Train the recognizer on all face images belonging to the logged-in user.
        Call this after a successful password login.

        :param face_paths: List of image file paths for this user (max 2)
        :param username: Username string (for logging)
        """
        self.is_trained = False
        self.current_user = username

        samples = []
        labels  = []

        for path in face_paths:
            if not os.path.exists(path):
                logger.warning(f"Face image not found: {path}")
                continue

            img = cv2.imread(path)
            if img is None:
                logger.warning(f"Could not read image: {path}")
                continue

            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
            )

            if len(faces) == 0:
                logger.warning(f"No face detected in {path} — skipping.")
                continue

            x, y, w, h = faces[0]
            face_crop    = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face_crop, (100, 100))
            samples.append(face_resized)
            labels.append(0)   # label 0 = authorized user

        if not samples:
            logger.error(f"No valid face samples found for user '{username}'.")
            return

        self.recognizer.train(samples, np.array(labels))
        self.is_trained = True
        logger.info(f"Face model trained for '{username}' with {len(samples)} sample(s).")

    def recognize(self, frame: np.ndarray) -> dict:
        """
        Detect and recognize faces in a video frame.

        Returns:
          authorized      : bool   — True if a known face matched
          face_detected   : bool   — True if any face was found in frame
          confidence      : float  — LBPH distance (lower = better match)
          matched_user    : str    — username if matched, else ""
          annotated_frame : ndarray
        """
        result = {
            "authorized":       False,
            "face_detected":    False,
            "confidence":       999.0,
            "matched_user":     "",
            "annotated_frame":  frame.copy()
        }

        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )

        if len(faces) == 0:
            return result

        result["face_detected"] = True

        for (x, y, w, h) in faces:
            face_crop    = gray[y:y+h, x:x+w]
            face_resized = cv2.resize(face_crop, (100, 100))

            color      = (0, 0, 255)   # Red default
            label_text = "UNAUTHORIZED"

            if self.is_trained:
                label, confidence = self.recognizer.predict(face_resized)
                result["confidence"] = float(confidence)

                if label == 0 and confidence < LBPH_CONFIDENCE_LIMIT:
                    result["authorized"]    = True
                    result["matched_user"]  = self.current_user
                    color      = (0, 255, 0)
                    label_text = f"{self.current_user.upper()} ({confidence:.0f})"
                else:
                    label_text = f"UNAUTHORIZED ({confidence:.0f})"
            else:
                label_text = "NO FACE MODEL"

            cv2.rectangle(result["annotated_frame"], (x, y), (x+w, y+h), color, 2)
            cv2.putText(
                result["annotated_frame"], label_text,
                (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2
            )

        return result

    def clear(self):
        """Clear trained model (call on logout)."""
        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.is_trained  = False
        self.current_user = ""
