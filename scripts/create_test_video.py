import os
import cv2

def resize_to_max(img, max_dim=640):
    h, w = img.shape[:2]
    if max(h, w) <= max_dim:
        return img
    scale = max_dim / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h))

img_dir = r"C:\Users\Strang3\Desktop\New folder"
output_video = r"edge/config/test_person.mp4"

os.makedirs(os.path.dirname(output_video), exist_ok=True)

files = sorted(os.listdir(img_dir))
images = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

if not images:
    print("No images found in New folder")
    exit(1)

# Read the first image to get dimensions after resize
first_img_path = os.path.join(img_dir, images[0])
first_img = cv2.imread(first_img_path)
first_resized = resize_to_max(first_img)
h, w, c = first_resized.shape

# Define codec and VideoWriter (mp4v codec)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_video, fourcc, 1.0, (w, h))

for img_name in images:
    img_path = os.path.join(img_dir, img_name)
    img = cv2.imread(img_path)
    if img is not None:
        img_resized = resize_to_max(img)
        # Force padding or resizing to exact size (w, h)
        if img_resized.shape[:2] != (h, w):
            img_resized = cv2.resize(img_resized, (w, h))
        # Add frame to video
        for _ in range(5): # 5 seconds per image
            out.write(img_resized)

out.release()
print(f"Created video: {output_video} with dimensions {w}x{h} and {len(images)*5} frames.")
