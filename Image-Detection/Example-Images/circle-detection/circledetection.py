from pathlib import Path
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

        print(f"  - Encrypted image saved to {encrypted_path}")

    except Exception as e:
        print(f"Encryption error: {e}")

# ===================== PROCESS =====================

def process_image(image_path):
    try:
        print(f"\nProcessing: {image_path}")

        img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print("  - Failed to load image")
            return

        # Normalize
        if len(img.shape) == 2:
            bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:
            bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            bgr = img

        bgr = cv2.GaussianBlur(bgr, (5, 5), 1)

        # ===================== RED MASK =====================

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        mask = (
            cv2.inRange(hsv, (0, 100, 100), (10, 255, 255)) |
            cv2.inRange(hsv, (170, 100, 100), (180, 255, 255))
        )

        mask = cv2.GaussianBlur(mask, (5, 5), 2)

        # ===================== EDGES =====================

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        # ===================== HOUGH =====================

        circles = cv2.HoughCircles(
            edges,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=50,
            param1=120,
            param2=18,  # slightly less strict
            minRadius=5,
            maxRadius=100
        )

        if circles is None:
            print("  - No circles detected")
            return

        circles = np.round(circles[0, :]).astype("int")

        best = None
        best_score = 0

        for (cx, cy, r) in circles:

            if cx - r < 0 or cy - r < 0 or cx + r >= bgr.shape[1] or cy + r >= bgr.shape[0]:
                continue

            # ===================== RING BAND =====================

            outer = np.zeros(mask.shape, dtype=np.uint8)
            inner = np.zeros(mask.shape, dtype=np.uint8)

            cv2.circle(outer, (cx, cy), r + 2, 255, -1)
            cv2.circle(inner, (cx, cy), r - 2, 255, -1)

            ring_band = cv2.subtract(outer, inner)

            # ===================== EDGE ON RING =====================

            ring_edges = np.count_nonzero(cv2.bitwise_and(edges, edges, mask=ring_band))
            ring_area = np.count_nonzero(ring_band)

            edge_ratio = ring_edges / max(1, ring_area)

            # ===================== RED ON RING =====================

            red_on_ring = np.count_nonzero(cv2.bitwise_and(mask, mask, mask=ring_band))
            red_ratio = red_on_ring / max(1, ring_area)

            # ===================== SCORE =====================

            score = (edge_ratio * 0.55) + (red_ratio * 0.45)

            # ===================== FILTER =====================

            if (
                edge_ratio >= 0.16 and     # allow a little less edge density
                red_ratio >= 0.22 and      # allow slightly weaker red signal
                score > best_score
            ):
                best_score = score
                best = (cx, cy, r)

        if best is None:
            print("  - No valid ring circles found")
            return

        cx, cy, r = best
        print(f"  - Ring circle detected at ({cx},{cy}) r={r} score={best_score:.2f}")

        # ===================== CROP =====================

        pad = int(r * 0.2)

        x1 = max(cx - r - pad, 0)
        y1 = max(cy - r - pad, 0)
        x2 = min(cx + r + pad, bgr.shape[1] - 1)
        y2 = min(cy + r + pad, bgr.shape[0] - 1)

        crop = img[y1:y2+1, x1:x2+1]

        if crop.size == 0:
            return

        out_path = output_folder / f"{image_path.stem}_cropped.png"

        if cv2.imwrite(str(out_path), crop):
            print(f"  - Saved cropped image to {out_path}")
            encrypt_image(out_path)

    except Exception as e:
        print(f"Processing error: {e}")

# ===================== MAIN =====================

if __name__ == "__main__":

    print(f"\nScanning: {USB_DRIVE}")

    image_files = sorted(USB_DRIVE.glob("*.png"))

    if not image_files:
        print("  - No PNG files found")
        exit()

    print(f"  - Found {len(image_files)} images")

    for path in image_files:
        p = multiprocessing.Process(target=process_image, args=(path,))
        p.start()
        p.join(IMAGE_TIMEOUT)

        if p.is_alive():
            print(f"  - TIMEOUT: {path}")
            p.terminate()
            p.join()
