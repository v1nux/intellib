"""
IntelliBreak — Recommendation Engine
Generates personalized productivity and work-life balance recommendations
based on ML predictions and session behavior patterns.
"""


def generate_recommendation(prediction_label, features, session_data=None):
    """
    Generate a personalized recommendation based on the productivity prediction
    and session behavior.

    Args:
        prediction_label: "Low", "Medium", or "High"
        features: dict with the 5 ML input features
        session_data: optional session dict for additional context

    Returns:
        dict with recommendation text, tips, and expected benefits
    """
    work_hours = features.get("average_daily_work_hours", 0)
    break_count = features.get("break_frequency_per_day", 0)
    focus_time = features.get("focus_time_minutes", 0)
    late_ratio = features.get("late_task_ratio", 0)
    feedback = features.get("real_time_feedback_score", 75)

    # Analyze behavior patterns
    patterns = _analyze_patterns(work_hours, break_count, focus_time,
                                  late_ratio, feedback, session_data)

    # Generate main recommendation based on prediction level
    if prediction_label == "High":
        rec = _high_productivity_rec(patterns)
    elif prediction_label == "Medium":
        rec = _medium_productivity_rec(patterns)
    else:
        rec = _low_productivity_rec(patterns)

    return rec


def _analyze_patterns(work_hours, break_count, focus_time, late_ratio,
                       feedback, session_data):
    """Identify behavior patterns from session data."""
    patterns = {
        "overworking": work_hours > 9,
        "underworking": work_hours < 4,
        "no_breaks": break_count == 0,
        "few_breaks": break_count <= 1,
        "many_breaks": break_count >= 5,
        "good_breaks": 2 <= break_count <= 4,
        "low_focus": focus_time < 60,
        "good_focus": focus_time >= 120,
        "high_focus": focus_time >= 180,
        "behind_schedule": late_ratio > 0.2,
        "on_track": late_ratio <= 0.1,
        "low_feedback": feedback < 65,
        "high_feedback": feedback >= 85,
    }

    # Check target completion if session data available
    if session_data and session_data.get("target_duration_minutes"):
        target = session_data["target_duration_minutes"]
        total = session_data.get("total_duration_minutes") or (work_hours * 60)
        if total > 0:
            patterns["target_met"] = total >= target * 0.8
            patterns["target_exceeded"] = total > target * 1.3
        else:
            patterns["target_met"] = False
            patterns["target_exceeded"] = False

    return patterns


def _high_productivity_rec(patterns):
    """Recommendations for High productivity prediction."""
    main_message = "Maintain your current work pattern and continue taking regular breaks."

    tips = [
        "Your focus-to-work ratio is excellent — keep it up!",
        "Consider documenting your productive work patterns for future reference.",
        "Share your strategies with colleagues to help improve team productivity."
    ]

    if patterns.get("overworking"):
        main_message = "Great productivity! But consider reducing work hours to maintain sustainability."
        tips.insert(0, "Your extended work hours may lead to burnout over time. "
                      "Try to keep sessions under 8 hours.")

    if patterns.get("no_breaks") or patterns.get("few_breaks"):
        tips.insert(0, "Even with high productivity, regular breaks help maintain "
                      "long-term cognitive performance.")

    if patterns.get("high_focus"):
        tips.append("Your sustained focus is impressive. Use the Pomodoro technique "
                    "to ensure you're also resting adequately.")

    benefits = [
        "Sustained high performance",
        "Healthy work-life balance maintenance",
        "Prevention of burnout",
        "Continued professional growth"
    ]

    return {
        "prediction": "High",
        "main_recommendation": main_message,
        "tips": tips[:4],
        "expected_benefits": benefits,
        "work_life_balance": _assess_work_life_balance(patterns),
        "burnout_risk": _assess_burnout_risk(patterns)
    }


def _medium_productivity_rec(patterns):
    """Recommendations for Medium productivity prediction."""
    main_message = "Increase focus sessions and reduce interruptions to improve productivity."

    tips = []

    if patterns.get("few_breaks") or patterns.get("no_breaks"):
        tips.append("Take more regular breaks (every 25-50 minutes). "
                    "Short breaks improve long-term focus and prevent mental fatigue.")
        main_message = "Add structured break intervals to boost your focus quality."

    if patterns.get("many_breaks"):
        tips.append("You're taking frequent breaks. Try extending your focus periods "
                    "between breaks to build deeper concentration.")
        main_message = "Extend focus periods between breaks to achieve deeper concentration."

    if patterns.get("behind_schedule"):
        tips.append("You're running behind schedule. Try breaking tasks into "
                    "smaller, manageable chunks with clear time targets.")

    if patterns.get("low_focus"):
        tips.append("Your focus time is below optimal. Minimize distractions — "
                    "close unnecessary tabs and notifications during work sessions.")

    if patterns.get("overworking"):
        tips.append("Long work sessions don't always mean better productivity. "
                    "Focus on quality work within a reasonable timeframe.")

    # Default tips if none triggered
    if not tips:
        tips = [
            "Structure your work in focused blocks of 25-50 minutes.",
            "Remove distractions during focus periods.",
            "Set specific, measurable goals for each session.",
        ]

    tips.append("Track your most productive hours and schedule important tasks accordingly.")

    benefits = [
        "Improved productivity awareness",
        "Better time management",
        "Enhanced focus quality",
        "Personalized work pattern optimization"
    ]

    return {
        "prediction": "Medium",
        "main_recommendation": main_message,
        "tips": tips[:4],
        "expected_benefits": benefits,
        "work_life_balance": _assess_work_life_balance(patterns),
        "burnout_risk": _assess_burnout_risk(patterns)
    }


def _low_productivity_rec(patterns):
    """Recommendations for Low productivity prediction."""
    main_message = ("Consider restructuring your work sessions with clearer goals "
                    "and regular break intervals.")

    tips = []

    if patterns.get("no_breaks") or patterns.get("few_breaks"):
        tips.append("Taking regular breaks is crucial! Work in focused bursts of "
                    "25 minutes (Pomodoro Technique) with 5-minute breaks.")

    if patterns.get("many_breaks"):
        tips.append("Too many breaks can fragment your focus. Try to work in "
                    "longer focused blocks before taking a break.")

    if patterns.get("behind_schedule"):
        tips.append("Break large tasks into smaller subtasks. Set realistic time "
                    "estimates and prioritize the most important work first.")

    if patterns.get("low_focus"):
        tips.append("Create a distraction-free workspace. Close social media, "
                    "silence notifications, and use focus mode on your devices.")

    if patterns.get("overworking"):
        tips.append("Working longer hours isn't helping. Focus on efficiency — "
                    "shorter, more intense work sessions often produce better results.")

    if patterns.get("underworking"):
        tips.append("Try to commit to at least 4-6 hours of focused work. "
                    "Start with small achievable goals and build from there.")

    if patterns.get("low_feedback"):
        tips.append("Your session patterns suggest room for improvement. "
                    "Try changing your work environment or time of day.")

    # Default tips
    if not tips:
        tips = [
            "Start each session with a clear goal and deadline.",
            "Use the Pomodoro Technique: 25 min work, 5 min break.",
            "Identify and eliminate your top 3 distractions.",
        ]

    tips.append("Consider changing your work environment or working during "
                "your peak energy hours.")

    benefits = [
        "Improved productivity awareness",
        "Personalized productivity recommendations",
        "Better work-life balance",
        "Data-driven productivity analysis",
        "Productivity trend monitoring"
    ]

    return {
        "prediction": "Low",
        "main_recommendation": main_message,
        "tips": tips[:4],
        "expected_benefits": benefits,
        "work_life_balance": _assess_work_life_balance(patterns),
        "burnout_risk": _assess_burnout_risk(patterns)
    }


def _assess_work_life_balance(patterns):
    """Assess work-life balance status."""
    if patterns.get("overworking"):
        return {
            "status": "Needs Attention",
            "message": "Your work hours are extending beyond healthy limits. "
                      "Consider setting firm boundaries for your work day."
        }
    elif patterns.get("underworking"):
        return {
            "status": "Review Needed",
            "message": "Your work duration seems short. Ensure you're allocating "
                      "enough focused time to meet your goals."
        }
    elif patterns.get("good_breaks") and patterns.get("on_track"):
        return {
            "status": "Healthy",
            "message": "Your work-life balance appears healthy. You're taking "
                      "appropriate breaks and managing your time well."
        }
    else:
        return {
            "status": "Acceptable",
            "message": "Your work-life balance is acceptable but could be improved "
                      "with more structured break patterns."
        }

def _assess_burnout_risk(patterns):
    """
    Calculate burnout risk using a multi-factor score instead of just work hours.
    Factors:
    - Overworking (+3 risk)
    - No breaks (+2 risk) or Few breaks (+1 risk)
    - Behind schedule (+1 risk)
    - Low feedback score (+1 risk)
    """
    risk_score = 0
    
    if patterns.get("overworking"):
        risk_score += 3
        
    if patterns.get("no_breaks"):
        risk_score += 2
    elif patterns.get("few_breaks"):
        risk_score += 1
        
    if patterns.get("behind_schedule"):
        risk_score += 1
        
    if patterns.get("low_feedback"):
        risk_score += 1
        
    if risk_score >= 4:
        return "High"
    elif risk_score >= 2:
        return "Moderate"
    else:
        return "Low"
