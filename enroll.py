import cv2
import face_recognition
import numpy as np
import os
import db
db.init_db()

KNOWN_FACES_DIR = "known_faces"
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

name = input("Enter the customer's name: ").strip()
phone = input("Enter phone number (optional): ").strip()
if not name:
    raise SystemExit("Name cannot be empty.")

# Kitne angles se photo leni hai
POSES = [
    "Look STRAIGHT at the camera",
    "Turn head slightly LEFT",
    "Turn head slightly RIGHT",
    "Look slightly UP",
    "Look slightly DOWN",
]

cap = cv2.VideoCapture(0)
encodings = []
pose_index = 0

print("Press SPACE to capture each pose. Press Q to quit.")

while pose_index < len(POSES):
    ret, frame = cap.read()
    if not ret:
        print("Could not read from webcam.")
        break

    display = frame.copy()
    cv2.putText(display, f"{pose_index + 1}/{len(POSES)}: {POSES[pose_index]}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(display, "SPACE = capture | Q = quit",
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.imshow("Enroll Customer", display)

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

    if key == ord(" "):
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb_frame)

        if len(face_locations) != 1:
            print("Need exactly ONE face in frame. Try again.")
            continue

        encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
        encodings.append(encoding)
        print(f"Captured pose {pose_index + 1}: {POSES[pose_index]}")
        pose_index += 1

cap.release()
cv2.destroyAllWindows()

if encodings:
    customer_id = db.add_customer(name, phone, encodings)
    print(f"Saved '{name}' in database with ID {customer_id} ({len(encodings)} face angles)")
else:
    print("Nothing saved.")