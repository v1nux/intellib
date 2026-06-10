"""
IntelliBreak — ML Engine
Trains Random Forest, Decision Tree, and KNN classifiers on the
remote_worker_productivity dataset, and provides prediction + comparison.
"""

import os
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler

# =========================================
# Configuration
# =========================================

DATASET_PATH = os.path.join(os.path.dirname(__file__), "remote_worker_productivity_1000.csv")

FEATURE_COLUMNS = [
    "average_daily_work_hours",
    "break_frequency_per_day",
    "focus_time_minutes",
    "late_task_ratio",
    "real_time_feedback_score"
]

TARGET_COLUMN = "productivity_label"

RANDOM_STATE = 42
TEST_SIZE = 0.4

# =========================================
# Module-level state (loaded once on import)
# =========================================

_models = {}
_scaler = None
_accuracies = {}
_reports = {}
_confusion_matrices = {}
_best_model_name = None
_is_trained = False


def _train_all_models():
    """Train all 3 models and compute accuracy metrics."""
    global _models, _scaler, _accuracies, _reports, _confusion_matrices
    global _best_model_name, _is_trained

    df = pd.read_csv(DATASET_PATH)

    # Select features and target
    X = df[FEATURE_COLUMNS].copy()
    y = df[TARGET_COLUMN].copy()

    # Split data
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )

    # Scale features for KNN (RF and DT don't need it, but we apply uniformly)
    _scaler = StandardScaler()
    X_train_scaled = _scaler.fit_transform(X_train)
    X_test_scaled = _scaler.transform(X_test)

    # Define models
    model_configs = {
        "Random Forest": RandomForestClassifier(
            n_estimators=100, random_state=RANDOM_STATE, n_jobs=-1
        ),
        "Decision Tree": DecisionTreeClassifier(
            random_state=RANDOM_STATE, max_depth=10
        ),
        "KNN": KNeighborsClassifier(
            n_neighbors=5, n_jobs=-1
        )
    }

    # Train and evaluate each model
    for name, model in model_configs.items():

        # KNN benefits from scaling; RF and DT are scale-invariant
        if name == "KNN":
            model.fit(X_train_scaled, y_train)
            preds = model.predict(X_test_scaled)
        else:
            model.fit(X_train, y_train)
            preds = model.predict(X_test)

        accuracy = accuracy_score(y_test, preds)
        report = classification_report(y_test, preds, output_dict=True)
        cm = confusion_matrix(y_test, preds, labels=["Low", "Medium", "High"])

        _models[name] = model
        _accuracies[name] = round(accuracy * 100, 2)
        _reports[name] = report
        _confusion_matrices[name] = cm.tolist()

    # Determine best model
    _best_model_name = max(_accuracies, key=_accuracies.get)

    _is_trained = True


def predict(features_dict):

    if not _is_trained:
        raise RuntimeError("Models not trained yet. Call init() first.")

    # Build feature array in correct order
    feature_values = [features_dict[col] for col in FEATURE_COLUMNS]
    X = np.array([feature_values])
    X_scaled = _scaler.transform(X)

    results = {}
    for name, model in _models.items():
        if name == "KNN":
            pred = model.predict(X_scaled)[0]
        else:
            pred = model.predict(X)[0]
        results[name] = pred

    # Get probability/confidence from best model
    best_model = _models[_best_model_name]
    if _best_model_name == "KNN":
        proba = best_model.predict_proba(X_scaled)[0]
    else:
        proba = best_model.predict_proba(X)[0]

    classes = best_model.classes_.tolist()
    confidence = {classes[i]: round(float(proba[i]) * 100, 1) for i in range(len(classes))}

    return {
        "predictions": {
            "random_forest": results.get("Random Forest"),
            "decision_tree": results.get("Decision Tree"),
            "knn": results.get("KNN")
        },
        "best_prediction": results.get(_best_model_name),
        "best_algorithm": _best_model_name,
        "confidence": confidence,
        "features_used": features_dict
    }


def get_model_comparison():

    if not _is_trained:
        raise RuntimeError("Models not trained yet.")

    comparison = {}
    for name in _models:
        report = _reports[name]
        comparison[name] = {
            "accuracy": _accuracies[name],
            "precision_avg": round(report["weighted avg"]["precision"] * 100, 2),
            "recall_avg": round(report["weighted avg"]["recall"] * 100, 2),
            "f1_avg": round(report["weighted avg"]["f1-score"] * 100, 2),
            "per_class": {
                label: {
                    "precision": round(report[label]["precision"] * 100, 2),
                    "recall": round(report[label]["recall"] * 100, 2),
                    "f1": round(report[label]["f1-score"] * 100, 2),
                    "support": report[label]["support"]
                }
                for label in ["Low", "Medium", "High"] if label in report
            },
            "confusion_matrix": _confusion_matrices[name]
        }

    return {
        "models": comparison,
        "best_model": _best_model_name,
        "best_accuracy": _accuracies[_best_model_name],
        "labels": ["Low", "Medium", "High"]
    }


def compute_features_from_session(session_data, breaks_data, daily_work_hours=None):

    from datetime import datetime, timezone

    start_time = datetime.fromisoformat(session_data["start_time"])

    # If session is still active, use current time; otherwise use end_time
    if session_data.get("end_time"):
        end_time = datetime.fromisoformat(session_data["end_time"])
    else:
        end_time = datetime.now(timezone.utc).replace(tzinfo=None)

    total_seconds = (end_time - start_time).total_seconds()
    total_minutes = total_seconds / 60.0
    total_hours = total_seconds / 3600.0

    # Guard against zero/negative
    if total_minutes < 0.1:
        total_minutes = 0.1
        total_hours = total_minutes / 60.0

    # --- Feature 1: Average Daily Work Hours ---
    # Use daily aggregate (other completed sessions today + current session)
    # to match the dataset's "average_daily_work_hours" semantics (~3.5–11.3 range).
    # Without aggregation, a 30-min session would produce 0.5 hours — far outside
    # the training range, causing unreliable model extrapolation.
    if daily_work_hours is not None:
        avg_daily_work_hours = round(daily_work_hours + total_hours, 2)
    else:
        avg_daily_work_hours = round(total_hours, 2)
    # Clamp to dataset range to prevent model extrapolation into unseen territory
    avg_daily_work_hours = max(3.5, min(12.0, avg_daily_work_hours))

    # --- Feature 2: Break Frequency Per Day ---
    break_count = len(breaks_data)

    # --- Feature 3: Focus Time Minutes ---
    total_break_minutes = 0.0
    for b in breaks_data:
        if b.get("duration_minutes") and b["duration_minutes"]:
            total_break_minutes += b["duration_minutes"]
        elif b.get("is_active") and b["is_active"] == 1:
            # Break is still active
            b_start = datetime.fromisoformat(b["start_time"])
            total_break_minutes += (end_time - b_start).total_seconds() / 60.0

    focus_time = max(0, total_minutes - total_break_minutes)

    # --- Feature 4: Late Task Ratio ---
    target_minutes = session_data.get("target_duration_minutes", 60)
    if total_minutes <= target_minutes:
        # On track or ahead of schedule
        late_task_ratio = 0.0
    else:
        # Overtime — ratio increases as user exceeds target
        overtime_ratio = (total_minutes - target_minutes) / target_minutes
        late_task_ratio = min(0.4, overtime_ratio)  # Cap at 0.4 (dataset max ~0.4)

    # --- Feature 5: Real-Time Feedback Score (AUTO-COMPUTED) ---
    # Heuristic based on session behavior patterns:
    #   - Focus ratio (focus time / total time) → higher = better
    #   - Break frequency appropriateness → moderate breaks = better
    #   - Time management (on track vs overtime) → on track = better
    feedback_score = _compute_feedback_score(
        total_minutes, focus_time, break_count, late_task_ratio, target_minutes
    )

    return {
        "average_daily_work_hours": round(avg_daily_work_hours, 2),
        "break_frequency_per_day": break_count,
        "focus_time_minutes": round(focus_time, 2),
        "late_task_ratio": round(late_task_ratio, 6),
        "real_time_feedback_score": feedback_score
    }


def _compute_feedback_score(total_minutes, focus_minutes, break_count,
                            late_task_ratio, target_minutes):

    score = 50.0  # Base score

    # Factor 1: Focus Ratio (0-18 points)
    if total_minutes > 0:
        focus_ratio = focus_minutes / total_minutes

        # Penalize micro-fragmented focus (breaking before 10 min of continuous work)
        avg_focus_stretch = focus_minutes / (break_count + 1)
        if avg_focus_stretch < 10 and break_count > 0:
            score += focus_ratio * 5
        else:
            score += focus_ratio * 18
    else:
        score += 9  # Neutral

    # Factor 2: Break Pattern (0-12 points)
    # Evaluate breaks per hour to normalize across session lengths
    if total_minutes > 0:
        breaks_per_hour = break_count / (total_minutes / 60)
    else:
        breaks_per_hour = 0

    if break_count == 0:
        if total_minutes < 60:
            score += 8   # Acceptable for short sprints
        else:
            score += 4   # Should take breaks in longer sessions
    elif breaks_per_hour <= 1.0:
        score += 12  # Optimal (up to 1 break per hour)
    elif breaks_per_hour <= 2.0:
        score += 8   # Slightly frequent
    elif breaks_per_hour <= 3.0:
        score += 4   # Very frequent
    else:
        score += 1   # Highly distracted (>3 breaks/hour)

    # Factor 3: Time Management (0-12 points)
    if late_task_ratio == 0:
        # Only award full points if meaningful progress has been made
        if target_minutes > 0 and (total_minutes / target_minutes) < 0.2:
            score += 6   # Session barely started, neutral score
        else:
            score += 12
    elif late_task_ratio < 0.1:
        score += 10
    elif late_task_ratio < 0.2:
        score += 7
    elif late_task_ratio < 0.3:
        score += 4
    else:
        score += 2

    # Factor 4: Session Consistency (0-8 points)
    if target_minutes > 0:
        completion_ratio = total_minutes / target_minutes
        if 0.8 <= completion_ratio <= 1.2:
            score += 8   # Hit the target window
        elif 0.5 <= completion_ratio <= 1.5:
            score += 5
        else:
            score += 2

    # Clamp to dataset range (50-100)
    return int(max(50, min(100, round(score))))


def init():
    """Initialize and train all models. Call this on app startup."""
    _train_all_models()


# Auto-train on import
init()
