"""
User Manager
Handles user accounts stored in users.json.
Each user can have up to MAX_FACES_PER_USER face images.
Passwords are hashed with SHA-256 (simple, no extra deps needed).
"""

import json
import os
import hashlib
import shutil
import logging
from typing import Optional

logger = logging.getLogger(__name__)

USERS_FILE = "users.json"
FACES_DIR  = "known_faces"
MAX_FACES_PER_USER = 2


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def _save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def register_user(username: str, password: str) -> tuple[bool, str]:
    """
    Create a new user account.
    Returns (success, message).
    """
    username = username.strip().lower()
    if not username or not password:
        return False, "Username and password are required."

    users = _load_users()
    if username in users:
        return False, "Username already exists."

    users[username] = {
        "password_hash": _hash_password(password),
        "faces": []   # list of face image filenames for this user
    }
    _save_users(users)

    # Create face folder for this user
    os.makedirs(os.path.join(FACES_DIR, username), exist_ok=True)
    logger.info(f"User registered: {username}")
    return True, "Account created successfully."


def verify_login(username: str, password: str) -> tuple[bool, str]:
    """
    Verify username + password.
    Returns (success, message).
    """
    username = username.strip().lower()
    users = _load_users()

    if username not in users:
        return False, "Invalid username or password."

    if users[username]["password_hash"] != _hash_password(password):
        return False, "Invalid username or password."

    return True, "Login successful."


def get_user(username: str) -> Optional[dict]:
    """Return user data dict or None."""
    users = _load_users()
    return users.get(username.strip().lower())


def get_user_faces(username: str) -> list[str]:
    """
    Return list of face image paths for a user.
    Paths are relative to project root.
    """
    user = get_user(username)
    if not user:
        return []
    folder = os.path.join(FACES_DIR, username.strip().lower())
    # Return only paths that actually exist on disk
    return [
        os.path.join(folder, f)
        for f in user.get("faces", [])
        if os.path.exists(os.path.join(folder, f))
    ]


def add_face(username: str, image_data: bytes, ext: str = "jpg") -> tuple[bool, str]:
    """
    Save a new face image for the user.
    Returns (success, message).
    image_data: raw bytes of the image file.
    """
    username = username.strip().lower()
    users = _load_users()

    if username not in users:
        return False, "User not found."

    current_faces = users[username].get("faces", [])
    if len(current_faces) >= MAX_FACES_PER_USER:
        return False, f"Maximum {MAX_FACES_PER_USER} faces allowed per account. Delete one first."

    folder = os.path.join(FACES_DIR, username)
    os.makedirs(folder, exist_ok=True)

    # Find next available slot (face_0 or face_1)
    for slot in range(MAX_FACES_PER_USER):
        filename = f"face_{slot}.{ext}"
        if filename not in current_faces:
            filepath = os.path.join(folder, filename)
            with open(filepath, "wb") as f:
                f.write(image_data)
            users[username]["faces"].append(filename)
            _save_users(users)
            logger.info(f"Face added for user '{username}': {filename}")
            return True, f"Face saved as {filename}."

    return False, "No available face slot."


def delete_face(username: str, filename: str) -> tuple[bool, str]:
    """
    Delete a face image for the user.
    Returns (success, message).
    """
    username = username.strip().lower()
    users = _load_users()

    if username not in users:
        return False, "User not found."

    faces = users[username].get("faces", [])
    if filename not in faces:
        return False, "Face not found."

    filepath = os.path.join(FACES_DIR, username, filename)
    if os.path.exists(filepath):
        os.remove(filepath)

    users[username]["faces"].remove(filename)
    _save_users(users)
    logger.info(f"Face deleted for user '{username}': {filename}")
    return True, "Face deleted."


def list_users() -> list[str]:
    """Return list of all usernames."""
    return list(_load_users().keys())


def face_count(username: str) -> int:
    """Return number of registered faces for a user."""
    user = get_user(username)
    if not user:
        return 0
    return len(user.get("faces", []))
