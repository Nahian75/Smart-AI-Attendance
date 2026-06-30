"""
Enroll an employee using a live snapshot from a specific camera.

WHY THIS EXISTS:
  ArcFace embeddings depend on face angle and lighting. If enrollment photos
  were taken frontally but the camera sees people from above (CCTV/staircase),
  the embeddings won't match at runtime.

  This script captures a live frame from the camera, lets you crop a face from
  it, and sends that face to the enrollment API — so the stored embedding
  matches the camera's actual viewing angle.

USAGE:
  python scripts/enroll_from_camera.py \\
    --camera-id 69b3e85b-10a5-4206-8e24-e5871ca87dc4 \\
    --employee-id <employee-uuid> \\
    --backend http://localhost:8080 \\
    --email admin@demo.com \\
    --password admin123

  The script will:
    1. Fetch a snapshot from the camera preview endpoint
    2. Open it in a window — click and drag to select the face region
    3. Send the cropped face to the backend /enroll endpoint
    4. The new embedding is synced to edge nodes within 60 seconds

REQUIREMENTS:
  pip install opencv-python requests
"""

import argparse
import sys
import requests
import cv2
import numpy as np
from io import BytesIO

# ── Argument parsing ──────────────────────────────────────────────────────────

parser = argparse.ArgumentParser(description="Enroll face from live camera snapshot")
parser.add_argument("--camera-id",   required=True,  help="Camera UUID from the dashboard")
parser.add_argument("--employee-id", required=True,  help="Employee UUID to enroll")
parser.add_argument("--backend",     default="http://localhost:8080", help="Backend URL")
parser.add_argument("--email",       default="admin@demo.com")
parser.add_argument("--password",    default="admin123")
parser.add_argument("--output",      default=None,   help="Save snapshot to this path (optional)")
args = parser.parse_args()

# ── Login ─────────────────────────────────────────────────────────────────────

print(f"Logging in to {args.backend} ...")
r = requests.post(f"{args.backend}/api/v1/auth/login",
                  json={"email": args.email, "password": args.password}, timeout=10)
r.raise_for_status()
token = r.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
print("Logged in.")

# ── Fetch camera snapshot ─────────────────────────────────────────────────────

print(f"Fetching snapshot from camera {args.camera_id} ...")
r = requests.get(f"{args.backend}/api/v1/cameras/{args.camera_id}/preview",
                 headers=headers, timeout=15)
if r.status_code != 200:
    print(f"ERROR: Could not fetch snapshot — {r.status_code}: {r.text}")
    sys.exit(1)

img_array = np.frombuffer(r.content, np.uint8)
frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
if frame is None:
    print("ERROR: Could not decode snapshot image.")
    sys.exit(1)

if args.output:
    cv2.imwrite(args.output, frame)
    print(f"Snapshot saved to {args.output}")

# ── Face selection ────────────────────────────────────────────────────────────

print("\nCamera snapshot loaded.")
print("Draw a rectangle around the face to enroll, then press ENTER or SPACE.")
print("Press ESC to cancel.\n")

roi = cv2.selectROI("Select face — press ENTER when done", frame,
                    fromCenter=False, showCrosshair=True)
cv2.destroyAllWindows()

x, y, w, h = roi
if w == 0 or h == 0:
    print("No region selected. Exiting.")
    sys.exit(0)

# Add 10% padding around selection
pad_x, pad_y = int(w * 0.10), int(h * 0.10)
fh, fw = frame.shape[:2]
x1 = max(0, x - pad_x)
y1 = max(0, y - pad_y)
x2 = min(fw, x + w + pad_x)
y2 = min(fh, y + h + pad_y)
face_crop = frame[y1:y2, x1:x2]

# Encode to JPEG
_, jpeg = cv2.imencode(".jpg", face_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
face_bytes = jpeg.tobytes()

print(f"Cropped face region: {x2-x1}×{y2-y1}px")

# ── Upload to enrollment endpoint ─────────────────────────────────────────────

print(f"Uploading face for employee {args.employee_id} ...")
r = requests.post(
    f"{args.backend}/api/v1/employees/{args.employee_id}/enroll",
    headers={"Authorization": f"Bearer {token}"},
    files={"file": ("face.jpg", face_bytes, "image/jpeg")},
    timeout=30,
)
if r.status_code == 200:
    result = r.json()
    print(f"\n✓ Enrolled successfully!")
    print(f"  Employee: {args.employee_id}")
    print(f"  Embeddings stored: {result.get('embeddings_stored', 1)}")
    print(f"  Version: {result.get('version', '?')}")
    print(f"\nEdge nodes will sync the new embedding within 60 seconds.")
else:
    print(f"ERROR: Enrollment failed — {r.status_code}: {r.text}")
    sys.exit(1)
