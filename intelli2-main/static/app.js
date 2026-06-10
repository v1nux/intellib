const API_BASE = "/api";
let liveUpdateInterval = null;
let sessionTimerInterval = null;
let sessionSeconds = 0;

// State
let isSessionActive = false;
let isOnBreak = false;
let currentSession = null;
// ==========================================
// Smart Inactivity Detection
// ==========================================
let lastActivityTime = Date.now();

document.addEventListener("mousemove", () => {
  lastActivityTime = Date.now();
});

document.addEventListener("keydown", () => {
  lastActivityTime = Date.now();
});

document.addEventListener("click", () => {
  lastActivityTime = Date.now();
});

setInterval(() => {
  const inactiveMinutes = (Date.now() - lastActivityTime) / 1000 / 60;

  if (inactiveMinutes >= 0.1) {
    // Set to 15 for production, using 0.1 for demo purposes
    askBreakConfirmation();
  }
}, 1000); // Check every second for demo purposes (set to 60000 for 1 minute in production)

let inactivityPopupShown = false;

function askBreakConfirmation() {
  if (inactivityPopupShown) return;

  inactivityPopupShown = true;

  const answer = confirm(
    "No activity detected for 15 minutes.\n\nAre you currently taking a break?",
  );

  if (answer) {
    startAutoBreak();
  }

  inactivityPopupShown = false;

  lastActivityTime = Date.now();
}

async function startAutoBreak() {
  try {
    const response = await fetch("/api/sessions/break/start", {
      method: "POST",
      credentials: "include",
    });

    if (response.ok) {
      isOnBreak = true;
      updateUIState();

      showToast("Break started automatically");
    }
  } catch (error) {
    console.error(error);
  }
}
// ==========================================
// Toast Notifications
// ==========================================
function showToast(message, type = "info") {
  const toast = document.getElementById("toast");
  if (!toast) return;

  toast.textContent = message;
  toast.className = `toast show ${type}`;

  setTimeout(() => {
    toast.className = "toast";
  }, 3000);
}

// ==========================================
// Authentication
// ==========================================
async function login(event) {
  event.preventDefault();
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();
    if (response.ok) {
      window.location.href = "/dashboard";
    } else {
      showToast(data.error || "Login failed", "error");
    }
  } catch (err) {
    showToast("Connection error", "error");
  }
}

async function register(event) {
  event.preventDefault();
  const full_name = document.getElementById("reg-fullname").value;
  const username = document.getElementById("reg-username").value;
  const password = document.getElementById("reg-password").value;

  try {
    const response = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ full_name, username, password }),
    });

    const data = await response.json();
    if (response.ok) {
      window.location.href = "/dashboard";
    } else {
      showToast(data.error || "Registration failed", "error");
    }
  } catch (err) {
    showToast("Connection error", "error");
  }
}

async function logout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
    window.location.href = "/login";
  } catch (err) {
    showToast("Logout failed", "error");
  }
}

// ==========================================
// Session Management
// ==========================================
async function checkActiveSession() {
  try {
    const response = await fetch(`${API_BASE}/sessions/active`);
    if (response.status === 401) {
      window.location.href = "/login";
      return;
    }

    const data = await response.json();
    if (data.active) {
      isSessionActive = true;
      isOnBreak = data.on_break;
      currentSession = data.session;

      // Calculate elapsed time
      const startTime = new Date(currentSession.start_time).getTime();
      sessionSeconds = Math.floor((Date.now() - startTime) / 1000);

      updateUIState();
      startTimer();
      startLiveUpdates();

      // Do an immediate fetch to populate stats
      fetchLivePrediction();
    } else {
      isSessionActive = false;
      updateUIState();
    }
  } catch (err) {
    console.error("Failed to check session state:", err);
  }
}

async function startSession(event) {
  event.preventDefault();
  const activityType = document.getElementById("activityType").value;
  const targetDuration = document.getElementById("targetDuration").value;

  try {
    const response = await fetch(`${API_BASE}/sessions/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        activity_type: activityType,
        target_duration_minutes: parseInt(targetDuration),
      }),
    });

    const data = await response.json();
    if (response.ok) {
      isSessionActive = true;
      isOnBreak = false;
      currentSession = data.session;
      sessionSeconds = 0;

      updateUIState();
      startTimer();
      startLiveUpdates();

      // Clear previous dashboard data
      document.getElementById("currentPrediction").textContent = "Analyzing...";
      document.getElementById("currentPrediction").className = "stat-value";

      showToast("Session started successfully!", "success");
    } else {
      showToast(data.error || "Failed to start session", "error");
    }
  } catch (err) {
    showToast("Connection error", "error");
  }
}

async function endSession() {
  try {
    const response = await fetch(`${API_BASE}/sessions/end`, {
      method: "POST",
    });
    const data = await response.json();

    if (response.ok) {
      isSessionActive = false;
      isOnBreak = false;
      currentSession = null;

      stopTimer();
      stopLiveUpdates();
      updateUIState();

      // Show final recommendation modal or alert
      alert(
        `Session Ended!\nFinal Prediction: ${data.prediction.best_prediction}\n\nRecommendation: ${data.recommendation.main_recommendation}`,
      );

      showToast("Session ended successfully!", "success");

      // Clear dashboard data
      document.getElementById("currentPrediction").textContent = "-";
      document.getElementById("currentPrediction").className = "stat-value";
      document.getElementById("focusScore").textContent = "0";
      document.getElementById("breakCount").textContent = "0";
    } else {
      showToast(data.error || "Failed to end session", "error");
    }
  } catch (err) {
    showToast("Connection error", "error");
  }
}

// ==========================================
// Breaks
// ==========================================
async function toggleBreak() {
  const endpoint = isOnBreak ? "/break/end" : "/break/start";

  try {
    const response = await fetch(`${API_BASE}/sessions${endpoint}`, {
      method: "POST",
    });
    const data = await response.json();

    if (response.ok) {
      isOnBreak = !isOnBreak;
      updateUIState();
      showToast(isOnBreak ? "Break started" : "Break ended", "success");
    } else {
      showToast(data.error || "Action failed", "error");
    }
  } catch (err) {
    showToast("Connection error", "error");
  }
}

// ==========================================
// Live Updates & Timer
// ==========================================
function startTimer() {
  if (sessionTimerInterval) clearInterval(sessionTimerInterval);

  sessionTimerInterval = setInterval(() => {
    if (!isOnBreak) {
      sessionSeconds++;
      updateTimerDisplay();
    }
  }, 1000);
  updateTimerDisplay();
}

function stopTimer() {
  if (sessionTimerInterval) clearInterval(sessionTimerInterval);
  document.getElementById("timerDisplay").textContent = "00:00:00";
}

function updateTimerDisplay() {
  const hours = Math.floor(sessionSeconds / 3600);
  const minutes = Math.floor((sessionSeconds % 3600) / 60);
  const seconds = sessionSeconds % 60;

  document.getElementById("timerDisplay").textContent =
    `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function startLiveUpdates() {
  if (liveUpdateInterval) clearInterval(liveUpdateInterval);

  // Poll every 5 seconds
  liveUpdateInterval = setInterval(fetchLivePrediction, 5000);
}

function stopLiveUpdates() {
  if (liveUpdateInterval) clearInterval(liveUpdateInterval);
}

async function fetchLivePrediction() {
  if (isOnBreak) return; // Don't poll while on break

  try {
    const response = await fetch(`${API_BASE}/predict/live`);
    const data = await response.json();

    if (response.ok && data.active) {
      updateDashboardStats(data);
    }
  } catch (err) {
    console.error("Live update failed:", err);
  }
}

// ==========================================
// UI Updates
// ==========================================
function updateUIState() {
  const setupPanel = document.getElementById("setupPanel");
  const activePanel = document.getElementById("activePanel");
  const breakBtn = document.getElementById("breakBtn");
  const timerDisplay = document.getElementById("timerDisplay");

  if (isSessionActive) {
    setupPanel.classList.add("hidden");
    activePanel.classList.remove("hidden");

    if (isOnBreak) {
      breakBtn.textContent = "End Break";
      breakBtn.className = "btn btn-primary btn-block";
      timerDisplay.classList.add("pulse-animation");
      document.getElementById("sessionStatus").textContent = "Status: ON BREAK";
    } else {
      breakBtn.textContent = "Take a Break";
      breakBtn.className = "btn btn-success btn-block";
      timerDisplay.classList.remove("pulse-animation");
      document.getElementById("sessionStatus").textContent =
        "Status: ACTIVE FOCUS";
    }
  } else {
    setupPanel.classList.remove("hidden");
    activePanel.classList.add("hidden");
  }
}

function updateDashboardStats(data) {
  // Prediction
  const predEl = document.getElementById("currentPrediction");
  predEl.textContent = data.prediction.best_prediction;

  const label = data.prediction.best_prediction.toLowerCase();
  predEl.className = `stat-value badge-${label}`;

  // ML Stats
  document.getElementById("focusScore").textContent = Math.round(
    data.features.real_time_feedback_score,
  );

  document.getElementById("breakCount").textContent =
    data.features.break_frequency_per_day;

  // Burnout & WLB
  document.getElementById("burnoutRisk").textContent =
    data.recommendation.burnout_risk;
  document.getElementById("wlbStatus").textContent =
    data.recommendation.work_life_balance.status;
}

// ==========================================
// Initialization
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
  // If on dashboard, check session state immediately
  if (window.location.pathname === "/dashboard") {
    checkActiveSession();

    // Fetch user info
    fetch(`${API_BASE}/auth/me`)
      .then((res) => res.json())
      .then((data) => {
        if (data.user) {
          document.getElementById("userGreeting").textContent =
            `Hello, ${data.user.full_name}`;
        }
      });

    // Event Listeners
    document
      .getElementById("startForm")
      .addEventListener("submit", startSession);
    document.getElementById("breakBtn").addEventListener("click", toggleBreak);
    document.getElementById("endBtn").addEventListener("click", endSession);
    document.getElementById("logoutBtn").addEventListener("click", logout);
  }

  // If on login page
  if (
    window.location.pathname === "/login" ||
    window.location.pathname === "/"
  ) {
    const loginForm = document.getElementById("loginForm");
    if (loginForm) loginForm.addEventListener("submit", login);
  }

  // If on register page
  if (window.location.pathname === "/register") {
    const registerForm = document.getElementById("registerForm");
    if (registerForm) registerForm.addEventListener("submit", register);
  }
});
