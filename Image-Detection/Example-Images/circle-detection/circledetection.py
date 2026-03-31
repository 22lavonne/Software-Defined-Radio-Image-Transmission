from pathlib import Path
import time
import cv2
import numpy as np
import multiprocessing
import math

# ===================== CONFIG =====================

STATIC_KEY = 123
IMAGE_TIMEOUT = 5  # seconds

# Use script location as project root
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

level1_dirs = sorted([p for p in media_base.iterdir() if p.is_dir()])
if not level1_dirs:
    raise RuntimeError("No directories found inside /media")

first_level1 = level1_dirs[0]

level2_dirs = sorted([p for p in first_level1.iterdir() if p.is_dir()])
if not level2_dirs:
    raise RuntimeError(f"No drives found inside {first_level1}")

USB_DRIVE = level2_dirs[0]

print(f"Using drive: {USB_DRIVE}")

# ===================== IMAGE SOURCE =====================

runtime_folder = USB_DRIVE
image_files = sorted(runtime_folder.glob("*.png"))

if not image_files:
    print(f"No PNG images found in {runtime_folder}")
    raise SystemExit

print(f"Found {len(image_files)} images")

# ===================== ENCRYPTION =====================

def encrypt_image(image_path):
    try:
        with open(image_path, "rb") as fin:
            image_data = fin.read()

        image_byte_array = bytearray(image_data)

        for i in range(len(image_byte_array)):
            image_byte_array[i] ^= STATIC_KEY

        encrypted_path = encrypted_folder / ("encrypted_" + image_path.name)

        with open(encrypted_path, "wb") as fout:
            fout.write(image_byte_array)

        print(f"  - Encrypted image saved to {encrypted_path}")

    except Exception as e:
        print(f"Encryption error: {e}")

# ===================== IMAGE PROCESSING =====================

def process_image(image_path):
    try:
        print(f"\nProcessing: {image_path}")

        captured_frame = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

        if captured_frame is None:
            print("  - Failed to load image, skipping")
            return

        # Normalize image format
        if len(captured_frame.shape) == 2:
            captured_frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_GRAY2BGR)
        elif captured_frame.shape[2] == 4:
            captured_frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_BGRA2BGR)
        else:
            captured_frame_bgr = captured_frame.copy()

        captured_frame_bgr = cv2.GaussianBlur(captured_frame_bgr, (3, 3), 0)

        # ===================== STRICT RED MASK =====================

        hsv = cv2.cvtColor(captured_frame_bgr, cv2.COLOR_BGR2HSV)

        # Tight red only: not broad red hues
        lower_red1 = np.array([0, 170, 170], dtype=np.uint8)
        upper_red1 = np.array([6, 255, 255], dtype=np.uint8)

        lower_red2 = np.array([174, 170, 170], dtype=np.uint8)
        upper_red2 = np.array([180, 255, 255], dtype=np.uint8)

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # ===================== CONTOUR-BASED CIRCLE DETECTION =====================

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_score = 0.0

        for cnt in contours:
            area = cv2.contourArea(cnt)

            # Reject tiny junk
            if area < 80:
                continue

            perimeter = cv2.arcLength(cnt, True)
            if perimeter == 0:
                continue

            # Circularity: 1.0 = perfect circle
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity < 0.85:
                continue

            (cx, cy), radius = cv2.minEnclosingCircle(cnt)
            cx, cy, radius = int(cx), int(cy), int(radius)

            if radius < 6 or radius > 60:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            rect_area = w * h
            if rect_area == 0:
                continue

            # Contour should fill its bounding box like a circle, not a smear
            fill_ratio = area / rect_area
            if fill_ratio < 0.70:
                continue

            # Must be close to square
            aspect_ratio = w / float(h)
            if aspect_ratio < 0.90 or aspect_ratio > 1.10:
                continue

            # Contour area should match enclosing circle reasonably well
            circle_area = math.pi * (radius ** 2)
            if circle_area <= 0:
                continue

            area_ratio = area / circle_area
            if area_ratio < 0.65 or area_ratio > 1.20:
                continue

            # Mean BGR inside contour: must be truly red-dominant
            contour_mask = np.zeros(mask.shape, dtype=np.uint8)
            cv2.drawContours(contour_mask, [cnt], -1, 255, -1)

            mean_bgr = cv2.mean(captured_frame_bgr, mask=contour_mask)
            b, g, r = mean_bgr[:3]

            if r < 120:
                continue
            if r < g * 1.6:
                continue
            if r < b * 1.6:
                continue

            # Score candidate
            score = (circularity * 0.5) + (fill_ratio * 0.2) + (area_ratio * 0.3)

            if score > best_score:
                best_score = score
                best = (cx, cy, radius)

        if best is not None:
            cx, cy, r = best
            print(f"  - Circle accepted at ({cx}, {cy}) radius {r} (score={best_score:.2f})")

            padding = int(round(r * 0.2))

            x_min = max(cx - r - padding, 0)
            y_min = max(cy - r - padding, 0)
            x_max = min(cx + r + padding, captured_frame.shape[1] - 1)
            y_max = min(cy + r + padding, captured_frame.shape[0] - 1)

            cropped = captured_frame[y_min:y_max + 1, x_min:x_max + 1]

            if cropped.size == 0:
                print("  - WARNING: Cropped region empty")
                return

            output_path = output_folder / f"{image_path.stem}_cropped.png"

            if cv2.imwrite(str(output_path), cropped):
                print(f"  - Saved cropped image to {output_path}")
                encrypt_image(output_path)
            else:
                print("  - Failed to write cropped image")
        else:
            print("  - No valid red circles found")

    except Exception as e:
        print(f"Processing error for {image_path}: {e}")

# ===================== MAIN =====================

if __name__ == "__main__":
    for image_path in image_files:
        p = multiprocessing.Process(target=process_image, args=(image_path,))
        p.start()
        p.join(IMAGE_TIMEOUT)

        if p.is_alive():
            print(f"  - TIMEOUT: {image_path}")
            p.terminate()
            p.join()
