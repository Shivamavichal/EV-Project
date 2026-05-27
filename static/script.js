/**
 * AI Smart EV Dashboard Script
 * Handles: status polling, manual control, face management, logs, logout.
 */

const CMD_LABELS = { F:"FORWARD", B:"BACKWARD", L:"LEFT", R:"RIGHT", S:"STOPPED" };

// ── Status Polling ────────────────────────────────────────────

async function fetchStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.status === 401) { window.location.href = "/login"; return; }
    if (!res.ok) return;
    updateUI(await res.json());
  } catch (_) {}
}

function updateUI(d) {
  // Header badge
  const hBadge = document.getElementById("vehicle-badge");
  const stV    = document.getElementById("st-vehicle");
  if (d.authorized) {
    hBadge.textContent = "🔓 UNLOCKED"; hBadge.className = "badge badge-unlocked";
    stV.textContent    = "UNLOCKED";    stV.className    = "value badge badge-unlocked";
  } else {
    hBadge.textContent = "🔒 LOCKED";   hBadge.className = "badge badge-locked";
    stV.textContent    = "LOCKED";      stV.className    = "value badge badge-locked";
  }

  setText("st-face-detected", d.face_detected ? "✅ Yes" : "❌ No");
  setText("st-face-auth",
    d.authorized
      ? `<span style="color:var(--green)">✅ AUTHORIZED</span>`
      : `<span style="color:var(--red)">❌ UNAUTHORIZED</span>`
  );
  setText("st-matched-user", d.matched_user
    ? `<span style="color:var(--green)">${d.matched_user}</span>` : "—");
  setText("st-gesture",  d.gesture  || "—");

  const cmdEl = document.getElementById("st-command");
  if (cmdEl) {
    cmdEl.textContent   = d.command || "S";
    cmdEl.style.background = cmdColor(d.command);
  }
  setText("st-movement", CMD_LABELS[d.last_command_sent] || "STOPPED");
  setText("st-port",   d.serial_port + (d.simulation_mode ? " (SIM)" : ""));
  setText("st-serial",
    d.serial_connected
      ? `<span style="color:var(--green)">🟢 Connected</span>`
      : `<span style="color:var(--red)">🔴 Disconnected</span>`
  );
  setText("st-distance", d.distance_cm > 0 ? `${d.distance_cm} cm` : "— cm");
  updateDistanceArc(d.distance_cm, d.obstacle_detected);
  setText("st-obstacle",
    d.obstacle_detected
      ? `<span style="color:var(--red)">⚠️ OBSTACLE!</span>`
      : `<span style="color:var(--green)">✅ Clear</span>`
  );
}

function setText(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = html;
}

function cmdColor(cmd) {
  return { F:"#3fb950", B:"#58a6ff", L:"#d29922", R:"#d29922", S:"#f85149" }[cmd] || "#58a6ff";
}

// ── Distance Arc ──────────────────────────────────────────────

function updateDistanceArc(dist, obstacle) {
  const arc = document.getElementById("distance-arc");
  const val = document.getElementById("distance-value");
  const msg = document.getElementById("obstacle-msg");
  if (!arc) return;

  val.textContent = dist > 0 ? `${dist} cm` : "-- cm";

  if (obstacle || (dist > 0 && dist < 10)) {
    arc.className = "arc danger";
    msg.textContent = "⚠️ OBSTACLE"; msg.className = "obstacle-msg danger";
  } else if (dist > 0 && dist < 30) {
    arc.className = "arc warning";
    msg.textContent = "⚠️ Getting Close"; msg.style.color = "var(--yellow)";
  } else {
    arc.className = "arc safe";
    msg.textContent = "✅ Clear"; msg.style.color = "var(--green)";
  }
}

// ── Manual Commands ───────────────────────────────────────────

async function sendCmd(cmd) {
  try {
    const res  = await fetch("/api/manual_command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd })
    });
    const data = await res.json();
    if (!data.success) showToast(data.error || "Blocked", "error");
  } catch (_) { showToast("Network error", "error"); }
}

async function emergencyStop() {
  await fetch("/api/emergency_stop", { method: "POST" });
  showToast("🚨 Emergency Stop!", "warning");
}

// ── Logout ────────────────────────────────────────────────────

async function logout() {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
}

// ── Face Management ───────────────────────────────────────────

let faceCount = (typeof INITIAL_FACES !== "undefined") ? INITIAL_FACES.length : 0;

async function captureFace() {
  showFaceMsg("Capturing…", "");
  try {
    const res  = await fetch("/api/faces/capture", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showFaceMsg("✅ " + data.message, "success");
      showToast("Face captured!", "success");
      setTimeout(() => location.reload(), 1200);
    } else {
      showFaceMsg("❌ " + data.message, "error");
    }
  } catch (_) { showFaceMsg("Network error", "error"); }
}

async function uploadFace(input) {
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append("file", input.files[0]);
  showFaceMsg("Uploading…", "");
  try {
    const res  = await fetch("/api/faces/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (data.success) {
      showFaceMsg("✅ " + data.message, "success");
      showToast("Face uploaded!", "success");
      setTimeout(() => location.reload(), 1200);
    } else {
      showFaceMsg("❌ " + data.message, "error");
    }
  } catch (_) { showFaceMsg("Network error", "error"); }
  input.value = "";
}

async function deleteFace(filename) {
  if (!confirm(`Delete face "${filename}"?`)) return;
  try {
    const res  = await fetch("/api/faces/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename })
    });
    const data = await res.json();
    if (data.success) {
      showToast("Face deleted.", "success");
      setTimeout(() => location.reload(), 800);
    } else {
      showToast(data.message, "error");
    }
  } catch (_) { showToast("Network error", "error"); }
}

function showFaceMsg(text, type) {
  const el = document.getElementById("face-msg");
  if (!el) return;
  el.textContent = text;
  el.className   = "auth-msg " + type;
}

// ── Logs ──────────────────────────────────────────────────────

async function loadLogs() {
  try {
    const res  = await fetch("/api/logs");
    const data = await res.json();
    const box  = document.getElementById("log-box");
    if (!box) return;
    box.innerHTML = data.logs.map(l => `<p>${esc(l.trim())}</p>`).join("");
    box.scrollTop = box.scrollHeight;
  } catch (_) {}
}

function esc(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// ── Toast ─────────────────────────────────────────────────────

function showToast(msg, type = "info") {
  document.getElementById("toast")?.remove();
  const t = document.createElement("div");
  t.id = "toast";
  t.textContent = msg;
  const c = { success:"#3fb950", error:"#f85149", warning:"#d29922", info:"#58a6ff" };
  Object.assign(t.style, {
    position:"fixed", bottom:"24px", right:"24px",
    background: c[type] || c.info, color:"#000",
    padding:"10px 18px", borderRadius:"8px",
    fontWeight:"600", zIndex:"9999", fontSize:"0.9rem",
    boxShadow:"0 4px 12px rgba(0,0,0,0.4)"
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ── Keyboard shortcuts ────────────────────────────────────────

document.addEventListener("keydown", e => {
  const map = { ArrowUp:"F", ArrowDown:"B", ArrowLeft:"L", ArrowRight:"R", " ":"S" };
  if (map[e.key]) { e.preventDefault(); sendCmd(map[e.key]); }
});
document.addEventListener("keyup", e => {
  if (["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key)) sendCmd("S");
});

// ── Init ──────────────────────────────────────────────────────

fetchStatus();
loadLogs();
setInterval(fetchStatus, 1000);
setInterval(loadLogs, 5000);
