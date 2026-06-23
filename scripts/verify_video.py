import cv2

video_path = r"edge/config/test_person.mp4"
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Failed to open video")
    exit(1)

print("Video opened successfully")
print("Frame count:", cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("FPS:", cap.get(cv2.CAP_PROP_FPS))

frame_idx = 0
while True:
    ok, frame = cap.read()
    if not ok:
        print(f"Read failed at frame {frame_idx}")
        break
    frame_idx += 1

print(f"Successfully read {frame_idx} frames.")
cap.release()
