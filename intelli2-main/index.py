import pandas as pd

# Machine Learning Libraries
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.metrics import confusion_matrix
from sklearn.metrics import classification_report

# =====================================
# STEP 1: Load Dataset
# =====================================

df = pd.read_csv("remote_worker_productivity_1000.csv")

print("Dataset Loaded Successfully!")
print()

# =====================================
# STEP 2: Display Columns
# =====================================

print("Dataset Columns:")
print(df.columns)
print()

# =====================================
# STEP 3: Select Input Features (X)
# =====================================

X = df[
    [
        'average_daily_work_hours',
        'break_frequency_per_day',
        'focus_time_minutes',
        'late_task_ratio',
        'real_time_feedback_score'
    ]
]

# =====================================
# STEP 4: Select Prediction Target (Y)
# =====================================

Y = df['productivity_label']

# =====================================
# STEP 5: Split Dataset
# =====================================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    Y,
    test_size=0.2,
    random_state=42
)

# =====================================
# STEP 6: Train Model
# =====================================

model = RandomForestClassifier(
    random_state=42
)

model.fit(X_train, y_train)

print("Model Training Complete!")
print()

# =====================================
# STEP 7: Predict
# =====================================

predictions = model.predict(X_test)

# =====================================
# STEP 8: Accuracy
# =====================================

accuracy = accuracy_score(
    y_test,
    predictions
)

print(f"Model Accuracy: {accuracy * 100:.2f}%")
print()

# =====================================
# STEP 9: Confusion Matrix
# =====================================

cm = confusion_matrix(
    y_test,
    predictions
)

print("Confusion Matrix:")
print(cm)
print()

# =====================================
# STEP 10: Classification Report
# =====================================

print("Classification Report:")
print(
    classification_report(
        y_test,
        predictions
    )
)

print(df['productivity_label'].value_counts())