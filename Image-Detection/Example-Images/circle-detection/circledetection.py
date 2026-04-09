from pathlib import Path
import cv2
import numpy as np
import time
# ===================== CONFIG =====================

STATIC_KEY = 123  # XOR encryption key

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR

# ===================== OUTPUT FOLDERS =====================

output_folder = PROJECT_ROOT / "output"
output_folder.mkdir(parents=True, exist_ok=True)

encrypted_folder = output_folder / "encrypted"
encrypted_folder.mkdir(parents=True, exist_ok=True)

# ===================== SELECT FIRST MEDIA DRIVE =====================

media_base = Path("/media")

if not media_base.exists():
    raise RuntimeError("/media does not exist")

media_users = sorted([p for p in media_base.iterdir() if p.is_dir()])
if not media_users:
    raise RuntimeError("No directories found inside /media")

first_media_user = media_users[0]

mounted_drives = sorted([p for p in first_media_user.iterdir() if p.is_dir()])
if not mounted_drives:
    raise RuntimeError(f"No drives found inside {first_media_user}")

USB_DRIVE = mounted_drives[0]

print(f"Using drive: {USB_DRIVE}")

# ===================== INPUT =====================

INPUT_BASE = USB_DRIVE  # change to / "mock-images" if needed

def get_input_images():
    patterns = ("*.png", "*.jpg", "*.jpeg")
    image_files = []
    for pattern in patterns:
        image_files.extend(INPUT_BASE.glob(pattern))
    return sorted(image_files)

# ===================== RED DETECTION =====================

def get_red_mask(image):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 200, 150], np.uint8)
    upper_red1 = np.array([5, 255, 255], np.uint8)

    lower_red2 = np.array([175, 200, 150], np.uint8)
    upper_red2 = np.array([180, 255, 255], np.uint8)

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    red_mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((7, 7), np.uint8)

    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    red_mask = cv2.dilate(red_mask, kernel, iterations=1)

    return red_mask

def detect_circles(red_mask):

    if red_mask is None or red_mask.size == 0:
        return []

    blurred = cv2.GaussianBlur(red_mask, (9, 9), 2)

    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1,
        minDist=blurred.shape[0] // 4,
        param1=100,
        param2=51,
        minRadius=15,
        maxRadius=100
    )

    if circles is None:
        return []

    circles = np.round(circles[0, :]).astype(int)
    return [tuple(c) for c in circles]

# ===================== ENCRYPT =====================

def encrypt_image(image_path):
    try:
        with open(image_path, 'rb') as fin:
            data = bytearray(fin.read())

        for i in range(len(data)):
            data[i] ^= STATIC_KEY

        encrypted_path = encrypted_folder / ("encrypted_" + image_path.name)

        with open(encrypted_path, 'wb') as fout:
            fout.write(data)

        print(f"    -> Encrypted: {encrypted_path}")

    except Exception as e:
        print(f"    -> Encryption error: {e}")

# ===================== MAIN =====================

if __name__ == "__main__":

    image_files = get_input_images()

    if not image_files:
        print(f"No images found in {INPUT_BASE}")
        exit()

    print(f"Reading images from: {INPUT_BASE}")
    print(f"Found {len(image_files)} images")
    print("--------------------------------------------------\n")

    for idx, image_path in enumerate(image_files, 1):
        print(f"{idx}/{len(image_files)}. Processing: {image_path}")

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)

        if image is None or image.size == 0:
            print("  - Failed to load image")
            continue

        # Detect red
        red_mask = get_red_mask(image)

        if cv2.countNonZero(red_mask) < 50:
            print("  - No red detected")
            continue

        # Detect circles
        circles = detect_circles(red_mask)

        if not circles:
            print("  - No red circle detected")
            continue

        # Pick largest circle
        x, y, r = max(circles, key=lambda c: c[2])
        print("  - Red circle detected")

        # Crop safely
        y_min = max(y - r, 0)
        y_max = min(y + r, image.shape[0])
        x_min = max(x - r, 0)
        x_max = min(x + r, image.shape[1])

        cropped = image[y_min:y_max, x_min:x_max]

        if cropped.size == 0:
            print("  - Empty crop, skipping")
            continue

        output_path = output_folder / f"{image_path.stem}_cropped.png"

        if cv2.imwrite(str(output_path), cropped):
            print(f"    -> Saved: {output_path}")
            encrypt_image(output_path)
        else:
            print("  - Failed to save image")

    print("\nDone.")
    


