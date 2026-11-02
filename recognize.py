import math
import time
import cv2
import face_recognition
import numpy as np
import requests

SERVER_URL = "http://127.0.0.1:8000"
import db

# ================= SETTINGS =================
TOLERANCE = 0.5
COOLDOWN_SECONDS = 60
SCAN_TIME = 2.0

WHITE = (255, 255, 255)          # BGR colors
GREEN = (89, 199, 52)            # iOS green
AMBER = (10, 159, 255)           # iOS orange
PILL_BG = (40, 40, 40)
FONT = cv2.FONT_HERSHEY_DUPLEX

# ============ DATABASE (pehle jaisa) ============
db.init_db()
known_encodings, known_ids, known_names = db.load_known_faces()
print(f"Loaded {len(known_encodings)} encodings for {len(set(known_ids))} customer(s)")

last_alert = {}


def trigger_alert(customer_id):
    info = db.get_customer_info(customer_id)
    print("\n" + "=" * 40)
    print(f"  RETURNING CUSTOMER: {info['name']}")
    print(f"  Last visit : {info['last_visit'] or 'First time recorded'}")
    print(f"  Last bought: {info['last_purchase'] or '-'}")
    print(f"  Likes      : {', '.join(info['preferences']) or '-'}")
    print("=" * 40 + "\n")

    # Dashboard ko alert bhejo
    try:
        requests.post(f"{SERVER_URL}/alert/{customer_id}", timeout=1)
    except requests.RequestException:
        print("(Server nahi mila, sirf terminal me alert dikha)")

    db.update_last_visit(customer_id)


# ============ ANIMATION HELPERS ============
def ease_out(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def blend(frame, overlay, alpha):
    return cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)


def draw_corners(frame, cx, cy, size, color, thickness=3):
    """Face ID jaise gol kone wale brackets."""
    half = int(size / 2)
    x1, y1, x2, y2 = cx - half, cy - half, cx + half, cy + half
    r = max(int(size * 0.12), 8)       # kone ka gol-pan
    L = max(int(size * 0.14), 10)      # seedhi line ki lambai
    aa = cv2.LINE_AA

    # (arc center, arc start-end angle, line1 start->end, line2 start->end)
    cv2.ellipse(frame, (x1 + r, y1 + r), (r, r), 0, 180, 270, color, thickness, aa)
    cv2.line(frame, (x1, y1 + r), (x1, y1 + r + L), color, thickness, aa)
    cv2.line(frame, (x1 + r, y1), (x1 + r + L, y1), color, thickness, aa)

    cv2.ellipse(frame, (x2 - r, y1 + r), (r, r), 0, 270, 360, color, thickness, aa)
    cv2.line(frame, (x2 - r, y1), (x2 - r - L, y1), color, thickness, aa)
    cv2.line(frame, (x2, y1 + r), (x2, y1 + r + L), color, thickness, aa)

    cv2.ellipse(frame, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness, aa)
    cv2.line(frame, (x2, y2 - r), (x2, y2 - r - L), color, thickness, aa)
    cv2.line(frame, (x2 - r, y2), (x2 - r - L, y2), color, thickness, aa)

    cv2.ellipse(frame, (x1 + r, y2 - r), (r, r), 0, 90, 180, color, thickness, aa)
    cv2.line(frame, (x1, y2 - r), (x1, y2 - r - L), color, thickness, aa)
    cv2.line(frame, (x1 + r, y2), (x1 + r + L, y2), color, thickness, aa)


def draw_dots(frame, pts, progress, color):
    """Halke dots jo scan ke saath dheere-dheere ubharte hain."""
    if not pts:
        return frame
    overlay = frame.copy()
    visible = int(len(pts) * min(1.0, progress * 1.3))
    for p in pts[:visible]:
        cv2.circle(overlay, p, 3, color, -1, cv2.LINE_AA)
    return blend(frame, overlay, 0.75)


def draw_scan_line(frame, cx, cy, size, elapsed):
    """Box ke andar upar-neeche chalti naram line (fade ke saath)."""
    half = int(size / 2)
    x1, x2 = cx - half + 8, cx + half - 8
    k = 0.5 - 0.5 * math.cos(elapsed / 1.0 * math.pi)
    y = int(cy - half + size * k)
    overlay = frame.copy()
    for i, a in enumerate([1.0, 0.6, 0.35, 0.18]):     # peeche fade hoti trail
        cv2.line(overlay, (x1, y - i * 4), (x2, y - i * 4), WHITE, 2, cv2.LINE_AA)
    return blend(frame, overlay, 0.45)


def draw_pill(frame, text, center_x, y, color, show_check, check_progress):
    """Neeche gol dark pill, uske andar (optional) checkmark + text."""
    scale, th = 0.7, 1
    (tw, thh), _ = cv2.getTextSize(text, FONT, scale, th)
    icon_w = 34 if show_check else 0
    pad = 20
    w = tw + icon_w + pad * 2
    h = 44
    x1, y1 = int(center_x - w / 2), int(y)
    x2, y2 = x1 + w, y1 + h
    r = h // 2

    overlay = frame.copy()
    cv2.rectangle(overlay, (x1 + r, y1), (x2 - r, y2), PILL_BG, -1)
    cv2.circle(overlay, (x1 + r, y1 + r), r, PILL_BG, -1, cv2.LINE_AA)
    cv2.circle(overlay, (x2 - r, y1 + r), r, PILL_BG, -1, cv2.LINE_AA)
    frame = blend(frame, overlay, 0.78)

    tx = x1 + pad + icon_w
    if show_check:
        ccx, ccy = x1 + pad + 10, y1 + r
        cv2.circle(frame, (ccx, ccy), 11, color, -1, cv2.LINE_AA)
        # checkmark dheere-dheere banta hai
        p1, p2, p3 = (ccx - 5, ccy), (ccx - 1, ccy + 4), (ccx + 6, ccy - 4)
        if check_progress > 0:
            m = min(1.0, check_progress * 2)
            e1 = (int(p1[0] + (p2[0] - p1[0]) * m), int(p1[1] + (p2[1] - p1[1]) * m))
            cv2.line(frame, p1, e1, WHITE, 2, cv2.LINE_AA)
        if check_progress > 0.5:
            m = (check_progress - 0.5) * 2
            e2 = (int(p2[0] + (p3[0] - p2[0]) * m), int(p2[1] + (p3[1] - p2[1]) * m))
            cv2.line(frame, p2, e2, WHITE, 2, cv2.LINE_AA)

    cv2.putText(frame, text, (tx, y1 + r + thh // 2), FONT, scale, WHITE, th, cv2.LINE_AA)
    return frame


# ============ MAIN ============
cap = cv2.VideoCapture(0)
process_this_frame = True
face_locations = []
face_points = []
face_labels = []
scan_start = None
smooth = {}    # har chehre ka smooth box: {index: (cx, cy, size)}

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame = cv2.flip(frame, 1)

    # ---------- PEHCHAAN (pehle jaisa) ----------
    if process_this_frame:
        small = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        locs_small = face_recognition.face_locations(rgb_small)
        face_encodings = face_recognition.face_encodings(rgb_small, locs_small)
        landmarks = face_recognition.face_landmarks(rgb_small, locs_small)

        face_locations = [(t * 4, r * 4, b * 4, l * 4) for (t, r, b, l) in locs_small]
        face_points = [
            [(x * 4, y * 4) for feature in lm.values() for (x, y) in feature]
            for lm in landmarks
        ]

        face_labels = []
        for encoding in face_encodings:
            name, cid = "New Customer", None

            if known_encodings:
                distances = face_recognition.face_distance(known_encodings, encoding)
                best = np.argmin(distances)
                if distances[best] <= TOLERANCE:
                    name, cid = known_names[best], known_ids[best]

            face_labels.append((name, cid))

            if cid is not None:
                now = time.time()
                if now - last_alert.get(cid, 0) > COOLDOWN_SECONDS:
                    last_alert[cid] = now
                    trigger_alert(cid)

    process_this_frame = not process_this_frame

    # ---------- ANIMATION (Face ID style) ----------
    if face_locations:
        if scan_start is None:
            scan_start = time.time()
        elapsed = time.time() - scan_start
        done = elapsed >= SCAN_TIME
        progress = min(1.0, elapsed / SCAN_TIME)

        for i, (loc, pts, label) in enumerate(zip(face_locations, face_points, face_labels)):
            top, right, bottom, left = loc
            tcx, tcy = (left + right) // 2, (top + bottom) // 2
            tsize = max(right - left, bottom - top) * 1.35

            # smooth movement (jhatka kam)
            if i in smooth:
                pcx, pcy, ps = smooth[i]
                cx = pcx + (tcx - pcx) * 0.35
                cy = pcy + (tcy - pcy) * 0.35
                size = ps + (tsize - ps) * 0.35
            else:
                cx, cy, size = tcx, tcy, tsize
            smooth[i] = (cx, cy, size)
            cx, cy, size_i = int(cx), int(cy), float(size)

            known = label[1] is not None
            color = WHITE if not done else (GREEN if known else AMBER)

            # brackets shuru me "andar se bahar" phailte hain
            grow = 0.85 + 0.15 * ease_out(elapsed / 0.5)
            draw_corners(frame, cx, cy, size_i * grow, color)

            if not done:
                frame = draw_dots(frame, pts, progress, WHITE)
                frame = draw_scan_line(frame, cx, cy, size_i, elapsed)
                frame = draw_pill(frame, "Scanning", cx, cy + size_i / 2 + 18,
                                  WHITE, False, 0)
            else:
                check_p = ease_out((elapsed - SCAN_TIME) / 0.5)
                text = f"Welcome back, {label[0]}" if known else "New Customer"
                frame = draw_pill(frame, text, cx, cy + size_i / 2 + 18,
                                  color, True if known else False, check_p)
    else:
        scan_start = None
        smooth.clear()
        frame = draw_pill(frame, "Looking for a face", frame.shape[1] // 2, 24,
                          WHITE, False, 0)

    cv2.imshow("Greetify - Recognition", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()