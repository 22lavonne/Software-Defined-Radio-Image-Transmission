from pathlib import Path
import time
import cv2
import numpy as np
import multiprocessing
import math

# ===================== CONFIG =====================

STATIC_KEY = 123  # Static key for XOR encryption
IMAGE_TIMEOUT = 5  # seconds

# Use script location as project root (NOT the USB)
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

runtime_folder = USB_DRIVE  # change to / "mock-images" if needed

image_files = sorted(runtime_folder.glob("*.png"))

if not image_files:
    print(f"No PNG images found in {runtime_folder}")
    exit()

print(f"Found {len(image_files)} images")

# ===================== ENCRYPTION =====================

def encrypt_image(image_path):
    try:
        with open(image_path, 'rb') as fin:
            image_data = fin.read()

        image_byte_array = bytearray(image_data)

        for i in range(len(image_byte_array)):
            image_byte_array[i] ^= STATIC_KEY

        encrypted_path = encrypted_folder / ("encrypted_" + image_path.name)

        with open(encrypted_path, 'wb') as fout:
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
            captured_frame_bgr = captured_frame

        captured_frame_bgr = cv2.medianBlur(captured_frame_bgr, 3)

        # ===================== STRICT RED MASK (HSV) =====================

        hsv = cv2.cvtColor(captured_frame_bgr, cv2.COLOR_BGR2HSV)

        lower_red1 = np.array([0, 150, 150])
        upper_red1 = np.array([8, 255, 255])

        lower_red2 = np.array([172, 150, 150])
        upper_red2 = np.array([180, 255, 255])

        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.GaussianBlur(mask, (5, 5), 2)


# ===================== EDGE DETECTION =====================

        edges = cv2.Canny(mask, 50, 150)

        # ===================== CIRCLE DETECTION =====================

        circles = cv2.HoughCircles(
            edges,
            cv2.HOUGH_GRADIENT,
            1,
            mask.shape[0] / 8,
            param1=100,
            param2=20,
            minRadius=5,
            maxRadius=60
        )

        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")

            best = None
            best_score = 0.0

            for (cx, cy, r) in circles:

                if cx - r < 0 or cy - r < 0 or cx + r >= captured_frame.shape[1] or cy + r >= captured_frame.shape[0]:
                    continue

                # Edge strength
                circ_mask = np.zeros(edges.shape, dtype=np.uint8)
                cv2.circle(circ_mask, (cx, cy), r, 255, 3)

                edge_pixels = np.count_nonzero(cv2.bitwise_and(edges, edges, mask=circ_mask))
                circumference = max(1.0, 2.0 * math.pi * r)
                edge_ratio = edge_pixels / circumference

                # Fill coverage
                fill_mask = np.zeros(mask.shape, dtype=np.uint8)
                cv2.circle(fill_mask, (cx, cy), r, 255, -1)

                masked_inside = np.count_nonzero(cv2.bitwise_and(mask, mask, mask=fill_mask))
                circle_area = math.pi * (r ** 2)
                coverage = masked_inside / max(1.0, circle_area)

                score = edge_ratio * 0.7 + coverage * 0.3

                if edge_ratio >= 0.3 and coverage >= 0.4 and score > best_score:
                    best_score = score
                    best = (cx, cy, r)

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
                print("  - No reliable circles passed checks")

        else:
            print("  - No circles detected")

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
