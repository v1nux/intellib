"""
IntelliBreak — Flask API Server
Main application entry point with all REST API routes.
"""

from flask import Flask, make_response, request, jsonify, session, render_template, redirect, url_for
from flask_cors import CORS
from functools import wraps
import os

import database as db
import ml_engine
import recommendations as rec

# =========================================
# App Configuration
# =========================================

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)
app.secret_key = "intellibreak-dev-secret-key-2025"
CORS(app, supports_credentials=True)

@app.before_request
def log_request_info():
    if request.path.startswith('/api/predict') or request.path == '/api/sessions/end':
        app.logger.debug('Request Path: %s Method: %s', request.path, request.method)
        app.logger.debug('Headers: %s', request.headers)
        app.logger.debug('Body: %s', request.get_data())

@app.after_request
def log_response_info(response):
    if request.path.startswith('/api/predict') or request.path == '/api/sessions/end':
        app.logger.debug('Response Status: %s', response.status)
    return response

# =========================================
# Auth Decorator
# =========================================

def login_required(f):
    """Simple session-based auth check."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Not authenticated"}), 401
        return f(*args, **kwargs)
    return decorated


# =========================================
# Page Routes
# =========================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard_page"))
    return redirect(url_for("login_page"))


@app.route("/login")
def login_page():
    return render_template("login.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/dashboard")
def dashboard_page():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    response = make_response(render_template("dashboard.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response 

@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    response = make_response(render_template("analytics.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login_page"))
    response = make_response(render_template("history.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "-1"
    return response

# =========================================
# Auth API Routes
# =========================================

@app.route("/api/auth/register", methods=["POST"])
def register():
    """Register a new user account."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    full_name = data.get("full_name", "").strip()

    if not username or not password or not full_name:
        return jsonify({"error": "Username, password, and full name are required"}), 400

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400

    if len(password) < 4:
        return jsonify({"error": "Password must be at least 4 characters"}), 400

    user = db.create_user(username, password, full_name)
    if not user:
        return jsonify({"error": "Username already exists"}), 409

    # Auto-login after registration
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]

    return jsonify({
        "message": "Registration successful",
        "user": user
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    """Login with username and password."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    user = db.get_user_by_username(username)
    if not user or user["password"] != password:
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"]
        }
    })


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    """Logout current user."""
    session.clear()
    response = jsonify({"message": "Logged out successfully"})
    response.set_cookie('session', '', expires=0)
    return response


@app.route("/api/auth/me", methods=["GET"])
@login_required
def get_me():
    """Get current authenticated user info."""
    user = db.get_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 404
    return jsonify({"user": user})


# =========================================
# Session API Routes
# =========================================

@app.route("/api/sessions/start", methods=["POST"])
@login_required
def start_session():
    """Start a new focus/work session."""
    user_id = session["user_id"]

    # Check for existing active session
    active = db.get_active_session(user_id)
    if active:
        return jsonify({
            "error": "You already have an active session. End it first.",
            "active_session": active
        }), 409

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    activity_type = data.get("activity_type", "").strip()
    target_duration = data.get("target_duration_minutes")

    if not activity_type:
        return jsonify({"error": "Activity type is required"}), 400

    if not target_duration or int(target_duration) < 1:
        return jsonify({"error": "Target duration must be at least 1 minute"}), 400

    sess = db.create_session(user_id, activity_type, int(target_duration))

    return jsonify({
        "message": "Session started",
        "session": sess
    }), 201


@app.route("/api/sessions/end", methods=["POST"])
@login_required
def end_session():
    """End the active session and generate final prediction."""
    user_id = session["user_id"]
    active = db.get_active_session(user_id)

    if not active:
        return jsonify({"error": "No active session found"}), 404

    # End the session (computes durations)
    ended_session = db.end_session(active["id"])

    # Get breaks for feature computation
    breaks = db.get_session_breaks(active["id"])

    # Fetch total daily work hours from other completed sessions today
    daily_hours = db.get_daily_work_hours(user_id, exclude_session_id=active["id"])

    # Compute features from the completed session
    features = ml_engine.compute_features_from_session(ended_session, breaks, daily_work_hours=daily_hours)

    # Get ML prediction
    prediction = ml_engine.predict(features)

    # Generate recommendation
    recommendation = rec.generate_recommendation(
        prediction["best_prediction"], features, ended_session
    )

    # Save final prediction to database
    db.save_prediction(
        session_id=active["id"],
        user_id=user_id,
        prediction_type="final",
        rf_pred=prediction["predictions"]["random_forest"],
        dt_pred=prediction["predictions"]["decision_tree"],
        knn_pred=prediction["predictions"]["knn"],
        best_pred=prediction["best_prediction"],
        best_algo=prediction["best_algorithm"],
        features=features,
        recommendation=recommendation["main_recommendation"]
    )

    return jsonify({
        "message": "Session ended",
        "session": ended_session,
        "prediction": prediction,
        "recommendation": recommendation
    })


@app.route("/api/sessions/active", methods=["GET"])
@login_required
def get_active_session():
    """Get the currently active session status."""
    user_id = session["user_id"]
    active = db.get_active_session(user_id)

    if not active:
        return jsonify({"active": False, "session": None})

    breaks = db.get_session_breaks(active["id"])
    has_break = db.has_active_break(active["id"])

    return jsonify({
        "active": True,
        "session": active,
        "breaks": breaks,
        "on_break": has_break
    })


@app.route("/api/sessions/history", methods=["GET"])
@login_required
def get_session_history():
    """Get session history for the current user."""
    user_id = session["user_id"]
    sessions = db.get_user_sessions(user_id)
    return jsonify({"sessions": sessions})


# =========================================
# Break API Routes
# =========================================

@app.route("/api/sessions/break/start", methods=["POST"])
@login_required
def start_break():
    """Start a break during the active session."""
    user_id = session["user_id"]
    active = db.get_active_session(user_id)

    if not active:
        return jsonify({"error": "No active session found"}), 404

    if db.has_active_break(active["id"]):
        return jsonify({"error": "Break already in progress"}), 409

    brk = db.start_break(active["id"])

    return jsonify({
        "message": "Break started",
        "break": brk
    })


@app.route("/api/sessions/break/end", methods=["POST"])
@login_required
def end_break():
    """End the current break."""
    user_id = session["user_id"]
    active = db.get_active_session(user_id)

    if not active:
        return jsonify({"error": "No active session found"}), 404

    brk = db.end_break(active["id"])
    if not brk:
        return jsonify({"error": "No active break found"}), 404

    return jsonify({
        "message": "Break ended",
        "break": brk
    })


# =========================================
# ML Prediction API Routes
# =========================================

@app.route("/api/predict/live", methods=["GET"])
@login_required
def predict_live():
    """
    Real-time prediction during an active session.
    Called by the frontend every 5 seconds for live dashboard updates.
    """
    user_id = session["user_id"]
    active = db.get_active_session(user_id)

    if not active:
        return jsonify({"error": "No active session", "active": False}), 404

    breaks = db.get_session_breaks(active["id"])

    # Fetch total daily work hours from other completed sessions today
    daily_hours = db.get_daily_work_hours(user_id, exclude_session_id=active["id"])

    # Compute current features from live session data
    features = ml_engine.compute_features_from_session(active, breaks, daily_work_hours=daily_hours)

    # Get prediction from all models
    prediction = ml_engine.predict(features)

    # Generate recommendation
    recommendation = rec.generate_recommendation(
        prediction["best_prediction"], features, active
    )

    # Save as a 'live' prediction (for tracking purposes)
    # Rate-limit to avoid bloating the database if called frequently (e.g. every 5 seconds)
    if not db.has_recent_live_prediction(active["id"], interval_seconds=30):
        db.save_prediction(
            session_id=active["id"],
            user_id=user_id,
            prediction_type="live",
            rf_pred=prediction["predictions"]["random_forest"],
            dt_pred=prediction["predictions"]["decision_tree"],
            knn_pred=prediction["predictions"]["knn"],
            best_pred=prediction["best_prediction"],
            best_algo=prediction["best_algorithm"],
            features=features,
            recommendation=recommendation["main_recommendation"]
        )

    return jsonify({
        "active": True,
        "session": active,
        "features": features,
        "prediction": prediction,
        "recommendation": recommendation
    })


@app.route("/api/predict/compare", methods=["GET"])
@login_required
def compare_models():
    """Get model comparison/accuracy data."""
    comparison = ml_engine.get_model_comparison()
    return jsonify(comparison)


# =========================================
# Dashboard API Routes
# =========================================

@app.route("/api/dashboard/stats", methods=["GET"])
@login_required
def get_stats():
    """Get aggregate dashboard statistics."""
    user_id = session["user_id"]
    stats = db.get_user_stats(user_id)
    return jsonify(stats)


@app.route("/api/dashboard/predictions", methods=["GET"])
@login_required
def get_prediction_history():
    """Get prediction history for analytics."""
    user_id = session["user_id"]
    predictions = db.get_user_prediction_history(user_id)
    return jsonify({"predictions": predictions})


# =========================================
# Run Server
# =========================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  IntelliBreak — ML-Based Productivity System")
    print("  Starting server on http://localhost:8000")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=8000, debug=True)
