"""
AI Smart EV - Main Flask Application
Multi-user with per-user face recognition (max 2 faces per account).

Flow:
  1. Register account (username + password)
  2. Login with password → face scan against YOUR faces → EV unlocks
  3. Manage faces (add/delete) from dashboard
"""

import json, logging, os, time, threading, io
import cv2
import numpy as np
from flask import (Flask, Response, jsonify, render_template,
                   request, session, redirect, url_for)

# ── Config ────────────────────────────────────────────────────
with open("config.json") as f:
    CONFIG = json.load(f)

# ── Logging ───────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/system_logs.txt"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── Project imports ───────────────────────────────────────────
from ai.face_recognition_cv import FaceRecognizer
from ai.gesture_control      import GestureController
from ai.camera_stream        import CameraStream
from hardware.serial_comm    import SerialComm
from auth.user_manager       import (register_user, verify_login,
                                     get_user_faces, add_face,
                                     delete_face, face_count, get_user)

# ── Shared AI / hardware objects ──────────────────────────────
face_recognizer    = FaceRecognizer()
gesture_controller = GestureController()

camera = CameraStream(camera_index=CONFIG["camera_index"])
camera.face_recognizer    = face_recognizer
camera.gesture_controller = gesture_controller
camera.start()

serial_comm = SerialComm(
    port=CONFIG["serial_port"],
    baud_rate=CONFIG["baud_rate"],
    simulation_mode=CONFIG["simulation_mode"]
)
serial_comm.connect()

# ── Flask ─────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("EV_SECRET_KEY", "ev-secret-change-me-2024")

# ── Safety watchdog ───────────────────────────────────────────
_last_sent_command = "S"
_command_lock      = threading.Lock()

def _safety_watchdog():
    timeout = CONFIG.get("gesture_timeout_seconds", 2)
    while True:
        time.sleep(0.2)
        state     = camera.get_state()
        hw_status = serial_comm.get_status()

        if not state["authorized"]:
            _safe_send("S"); continue
        if hw_status["obstacle_detected"]:
            _safe_send("S"); continue
        if time.time() - state.get("last_gesture_time", 0) > timeout:
            _safe_send("S"); continue

        _safe_send(state["command"])

def _safe_send(cmd: str):
    global _last_sent_command
    with _command_lock:
        if cmd != _last_sent_command:
            serial_comm.send_command(cmd)
            _last_sent_command = cmd

threading.Thread(target=_safety_watchdog, daemon=True).start()

# ── Auth helpers ──────────────────────────────────────────────
def logged_in_user() -> str:
    """Return username from session, or empty string."""
    return session.get("username", "")

def require_login(f):
    """Decorator: redirect to login if not logged in."""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not logged_in_user():
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper

# ── Page routes ───────────────────────────────────────────────

@app.route("/")
def root():
    if logged_in_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login_page"))

@app.route("/login")
def login_page():
    if logged_in_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/register")
def register_page():
    return render_template("register.html")

@app.route("/dashboard")
@require_login
def dashboard():
    user = logged_in_user()
    faces = get_user_faces(user)
    face_names = [os.path.basename(p) for p in faces]
    return render_template("index.html", config=CONFIG,
                           username=user, user_faces=face_names,
                           max_faces=2)

# ── Auth API ──────────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def api_register():
    data     = request.get_json()
    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()
    ok, msg  = register_user(username, password)
    return jsonify({"success": ok, "message": msg}), (200 if ok else 400)

@app.route("/api/login", methods=["POST"])
def api_login():
    data     = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = (data.get("password") or "").strip()

    ok, msg = verify_login(username, password)
    if not ok:
        return jsonify({"success": False, "message": msg}), 401

    # Password OK → load this user's faces into the recognizer
    session["username"]      = username
    session["face_verified"] = False   # still needs face scan

    faces = get_user_faces(username)
    if faces:
        face_recognizer.train_for_user(faces, username)
        logger.info(f"Face model loaded for '{username}' ({len(faces)} face(s)).")
    else:
        face_recognizer.clear()
        logger.warning(f"User '{username}' has no registered faces.")

    # Reset camera auth state
    camera.state["authorized"] = False

    return jsonify({
        "success":    True,
        "message":    msg,
        "has_faces":  len(faces) > 0,
        "face_count": len(faces)
    })

@app.route("/api/logout", methods=["POST"])
def api_logout():
    username = logged_in_user()
    session.clear()
    face_recognizer.clear()
    camera.state["authorized"] = False
    _safe_send("S")
    logger.info(f"User '{username}' logged out.")
    return jsonify({"success": True})

# ── Face management API ───────────────────────────────────────

@app.route("/api/faces", methods=["GET"])
@require_login
def api_list_faces():
    """List face filenames for the logged-in user."""
    user  = logged_in_user()
    paths = get_user_faces(user)
    names = [os.path.basename(p) for p in paths]
    return jsonify({"faces": names, "count": len(names), "max": 2})

@app.route("/api/faces/capture", methods=["POST"])
@require_login
def api_capture_face():
    """
    Capture current webcam frame and save as a face for this user.
    The face must be visible in the frame.
    """
    user  = logged_in_user()
    count = face_count(user)
    if count >= 2:
        return jsonify({"success": False,
                        "message": "Maximum 2 faces already registered. Delete one first."}), 400

    frame = camera.get_frame()
    if frame is None:
        return jsonify({"success": False, "message": "Camera not ready."}), 500

    # Verify a face is actually visible before saving
    gray  = face_recognizer.face_cascade.detectMultiScale(
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
        scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
    )
    if len(gray) == 0:
        return jsonify({"success": False,
                        "message": "No face detected in frame. Look at the camera and try again."}), 400

    # Encode frame to JPEG bytes
    _, buf = cv2.imencode(".jpg", frame)
    ok, msg = add_face(user, buf.tobytes(), ext="jpg")
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    # Retrain recognizer with updated faces
    faces = get_user_faces(user)
    face_recognizer.train_for_user(faces, user)
    logger.info(f"Face captured and saved for '{user}'.")
    return jsonify({"success": True, "message": msg, "face_count": len(faces)})

@app.route("/api/faces/upload", methods=["POST"])
@require_login
def api_upload_face():
    """Upload a face photo file for this user."""
    user  = logged_in_user()
    count = face_count(user)
    if count >= 2:
        return jsonify({"success": False,
                        "message": "Maximum 2 faces already registered."}), 400

    if "file" not in request.files:
        return jsonify({"success": False, "message": "No file provided."}), 400

    file      = request.files["file"]
    img_bytes = file.read()

    # Validate it contains a detectable face
    nparr = np.frombuffer(img_bytes, np.uint8)
    img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return jsonify({"success": False, "message": "Invalid image file."}), 400

    gray_faces = face_recognizer.face_cascade.detectMultiScale(
        cv2.cvtColor(img, cv2.COLOR_BGR2GRAY),
        scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)
    )
    if len(gray_faces) == 0:
        return jsonify({"success": False,
                        "message": "No face detected in uploaded image."}), 400

    ok, msg = add_face(user, img_bytes, ext="jpg")
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    faces = get_user_faces(user)
    face_recognizer.train_for_user(faces, user)
    return jsonify({"success": True, "message": msg, "face_count": len(faces)})

@app.route("/api/faces/delete", methods=["POST"])
@require_login
def api_delete_face():
    """Delete a face by filename for the logged-in user."""
    user     = logged_in_user()
    data     = request.get_json()
    filename = data.get("filename", "")

    ok, msg = delete_face(user, filename)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    # Retrain with remaining faces
    faces = get_user_faces(user)
    if faces:
        face_recognizer.train_for_user(faces, user)
    else:
        face_recognizer.clear()
        camera.state["authorized"] = False

    return jsonify({"success": True, "message": msg, "face_count": len(faces)})

# ── Camera & status ───────────────────────────────────────────

@app.route("/video_feed")
@require_login
def video_feed():
    return Response(camera.generate_mjpeg(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/api/status")
@require_login
def api_status():
    state = camera.get_state()
    hw    = serial_comm.get_status()
    user  = logged_in_user()
    return jsonify({
        "username":          user,
        "face_count":        face_count(user),
        "authorized":        state["authorized"],
        "face_detected":     state["face_detected"],
        "face_confidence":   state["face_confidence"],
        "matched_user":      state.get("matched_user", ""),
        "gesture":           state["gesture"],
        "command":           state["command"],
        "hand_detected":     state["hand_detected"],
        "serial_connected":  hw["connected"],
        "simulation_mode":   hw["simulation_mode"],
        "serial_port":       hw["port"],
        "last_command_sent": hw["last_command"],
        "distance_cm":       hw["distance_cm"],
        "obstacle_detected": hw["obstacle_detected"],
        "vehicle_status":    "UNLOCKED" if state["authorized"] else "LOCKED"
    })

# ── Control API ───────────────────────────────────────────────

@app.route("/api/manual_command", methods=["POST"])
@require_login
def manual_command():
    data = request.get_json()
    cmd  = (data.get("command") or "S").upper()
    if cmd not in {"F", "B", "L", "R", "S"}:
        return jsonify({"success": False, "error": "Invalid command"}), 400

    state = camera.get_state()
    hw    = serial_comm.get_status()

    if cmd == "S":
        _safe_send("S")
        return jsonify({"success": True, "command": cmd})
    if not state["authorized"]:
        return jsonify({"success": False, "error": "Vehicle locked"}), 403
    if hw["obstacle_detected"]:
        return jsonify({"success": False, "error": "Obstacle detected"}), 403

    _safe_send(cmd)
    return jsonify({"success": True, "command": cmd})

@app.route("/api/emergency_stop", methods=["POST"])
def emergency_stop():
    serial_comm.send_command("S")
    global _last_sent_command
    with _command_lock:
        _last_sent_command = "S"
    logger.warning("EMERGENCY STOP triggered.")
    return jsonify({"success": True})

# ── Logs & ports ──────────────────────────────────────────────

@app.route("/api/logs")
@require_login
def get_logs():
    try:
        with open("logs/system_logs.txt") as f:
            lines = f.readlines()
        return jsonify({"logs": lines[-50:]})
    except FileNotFoundError:
        return jsonify({"logs": []})

@app.route("/api/ports")
def list_ports():
    return jsonify({"ports": SerialComm.list_available_ports()})

# ── Entry point ───────────────────────────────────────────────
if __name__ == "__main__":
    logger.info(f"Starting Smart EV Dashboard on port {CONFIG['flask_port']}")
    app.run(host=CONFIG["flask_host"], port=CONFIG["flask_port"],
            debug=False, threaded=True)
