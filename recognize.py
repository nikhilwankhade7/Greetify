import time
import cv2
import face_recognition
import numpy as np
import db

TOLERANCE = 0.5
COOLDOWN_SECONDS = 60   # ek customer ka dobara alert itne second baad

db.init_db()
known_encodings, known_ids, known_names = db.load_known_faces()
print(f"Loaded {len(known_encodings)} encodings for {len(set(known_ids))} customer(s)")

last_alert = {}   # {customer_id: aakhri alert ka time}


def trigger_alert(customer_id):
    """Abhi terminal me print. Phase 3-4 me ye dashboard ko bhejega."""
    info = db.get_customer_info(customer_id)
    print("\n" + "=" * 40)
    print(f"  RETURNING CUSTOMER: {info['name']}")
    print(f"  Last visit : {info['last_visit'] or 'First time recorded'}")
    print(f"  Last bought: {info['last_purchase'] or '-'}")
    print(f"  Likes      : {', '.join(info['preferences']) or '-'}")
    print("=" * 40 + "\n")
    db.update_last_visit(customer_id)   # alert ke BAAD update karo


cap = cv2.VideoCapture(0)
process_this_frame = True
face_locations = []
face_labels = []   # [(naam, customer_id), ...]

while True:
    ret, frame = cap.read()
    if not ret:
        break

    if process_this_frame:
        small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        face_locations = face_recognition.face_locations(rgb_small)
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

        face_labels = []
        for encoding in face_encodings:
            name, cid = "New Customer", None

            if known_encodings:
                distances = face_recognition.face_distance(known_encodings, encoding)
                best = np.argmin(distances)
                if distances[best] <= TOLERANCE:
                    name, cid = known_names[best], known_ids[best]

            face_labels.append((name, cid))

            # Cooldown check: kya is customer ka alert abhi bheja tha?
            if cid is not None:
                now = time.time()
                if now - last_alert.get(cid, 0) > COOLDOWN_SECONDS:
                    last_alert[cid] = now
                    trigger_alert(cid)

    process_this_frame = not process_this_frame

    for (top, right, bottom, left), (name, cid) in zip(face_locations, face_labels):
        top, right, bottom, left = top * 4, right * 4, bottom * 4, left * 4
        color = (0, 255, 0) if cid is not None else (0, 165, 255)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, bottom - 30), (right, bottom), color, cv2.FILLED)
        cv2.putText(frame, name, (left + 6, bottom - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

    cv2.imshow("Greetify - Recognition", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()