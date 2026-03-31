from pathlib import Path
import time
import cv2
import numpy as np
import multiprocessing
import math

# ===================== CONFIG =====================

STATIC_KEY = 123  # Static key for XOR encryption

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# ===================== OUTPUT FOLDERS =====================

output_folder = PROJECT_ROOT / "output"
output_folder.mkdir(parents=True, exist_ok=True)

encrypted_folder = output_folder / "encrypted"
encrypted_folder.mkdir(parents=True, exist_ok=True)

IMAGE_TIMEOUT = 5

# ===================== LINUX MOUNT DETECTION =====================

def get_mount_points():
    mount_points = []
    for base in [Path("/mnt"), Path("/media")]:
        if base.exists():
            for path in base.iterdir():
                if path.is_dir():
                    mount_points.append(path)
    return mount_points

# ===================== ENCRYPTION =====================

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

# ===================== IMAGE PROCESSING =====================

def process_image(image_path):
    try:
        print(f"\nProcessing: {image_path}")

        img = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print("  - Failed to load image")
            return

        # Normalize channels
        if len(img.shape) == 2:
            bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        elif img.shape[2] == 4:
            bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            bgr = img

        bgr = cv2.medianBlur(bgr, 3)

        # ===================== COLOR MASK =====================

        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2Lab)
        lab_mask = cv2.inRange(
            lab,
            np.array([30, 160, 160]),
            np.array([180, 255, 255])
        )

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)

        lower_red1 = np.array([0, 120, 120])
        upper_red1 = np.array([10, 255, 255])

        lower_red2 = np.array([170, 120, 120])
        upper_red2 = np.array([180, 255, 255])

        hsv_mask = cv2.inRange(hsv, lower_red1, upper_red1) | \
                   cv2.inRange(hsv, lower_red2, upper_red2)

        mask = cv2.bitwise_and(lab_mask, hsv_mask)
        mask = cv2.GaussianBlur(mask, (5, 5), 2)

        # ===================== CIRCLE DETECTION =====================

        circles = cv2.HoughCircles(
            mask,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=mask.shape[0] / 6,
            param1=120,
            param2=28,  # slightly less strict
            minRadius=5,
            maxRadius=80
        )

        if circles is None:
            print("  - No circles detected")
            return

        circles = np.round(circles[0, :]).astype("int")

        edges = cv2.Canny(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), 50, 150)

        best = None
        best_score = 0

        for (cx, cy, r) in circles:

            if cx - r < 0 or cy - r < 0 or cx + r >= bgr.shape[1] or cy + r >= bgr.shape[0]:
                continue

            # ===================== EDGE RATIO =====================

            circ_mask = np.zeros(edges.shape, dtype=np.uint8)
            cv2.circle(circ_mask, (cx, cy), r, 255, 3)

            edge_pixels = np.count_nonzero(cv2.bitwise_and(edges, edges, mask=circ_mask))
            circumference = max(1.0, 2 * math.pi * r)
            edge_ratio = edge_pixels / circumference

            # ===================== COVERAGE =====================

            fill_mask = np.zeros(mask.shape, dtype=np.uint8)
            cv2.circle(fill_mask, (cx, cy), r, 255, -1)

            masked_inside = np.count_nonzero(cv2.bitwise_and(mask, mask, mask=fill_mask))
            circle_area = math.pi * r * r
            coverage = masked_inside / max(1.0, circle_area)

            # Allow filled circles but reject extreme blobs
            if coverage > 0.95:
                continue

            # ===================== INNER EDGE NOISE =====================

            inner_edges = np.count_nonzero(cv2.bitwise_and(edges, edges, mask=fill_mask))
            edge_density_inside = inner_edges / max(1.0, circle_area)

            # ===================== CIRCULARITY =====================

            contours, _ = cv2.findContours(
                cv2.bitwise_and(mask, fill_mask),
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            circularity = 0

            if contours:
                cnt = max(contours, key=cv2.contourArea)
                area = cv2.contourArea(cnt)
                perimeter = cv2.arcLength(cnt, True)

                if perimeter > 0:
                    circularity = 4 * math.pi * area / (perimeter ** 2)

            # ===================== RING CONSISTENCY =====================

            angles_hit = 0
            total_angles = 0

            for angle in range(0, 360, 10):
                rad = np.deg2rad(angle)
                x = int(cx + r * np.cos(rad))
                y = int(cy + r * np.sin(rad))

                if 0 <= x < edges.shape[1] and 0 <= y < edges.shape[0]:
                    total_angles += 1
                    if edges[y, x] > 0:
                        angles_hit += 1

            ring_consistency = angles_hit / max(1, total_angles)

            # ===================== FINAL FILTER =====================

            score = (edge_ratio * 0.5) + (coverage * 0.2) + (ring_consistency * 0.3)

            if (
                0.35 <= coverage <= 0.95 and
                edge_ratio >= 0.25 and
                circularity >= 0.65 and
                edge_density_inside <= 0.25 and
                ring_consistency >= 0.4 and
                score > best_score
            ):
                best_score = score
                best = (cx, cy, r)

        if best is None:
            print("  - No reliable circles passed checks")
            return

        cx, cy, r = best
        print(f"  - Circle accepted at ({cx}, {cy}) radius {r} score={best_score:.2f}")

        # ===================== CROP =====================

        pad = int(r * 0.2)

        x1 = max(cx - r - pad, 0)
        y1 = max(cy - r - pad, 0)
        x2 = min(cx + r + pad, bgr.shape[1] - 1)
        y2 = min(cy + r + pad, bgr.shape[0] - 1)

        crop = img[y1:y2+1, x1:x2+1]

        if crop.size == 0:
            print("  - Empty crop")
            return

        out_path = output_folder / f"{image_path.stem}_cropped.png"

        if cv2.imwrite(str(out_path), crop):
            print(f"  - Saved cropped image to {out_path}")
            encrypt_image(out_path)
        else:
            print("  - Failed to save image")

    except Exception as e:
        print(f"Processing error: {e}")

# ===================== MAIN =====================

if __name__ == "__main__":

    mounts = get_mount_points()

    if not mounts:
        print("No mounted drives found")
        exit()

    print("Mounted drives:")
    for m in mounts:
        print(f"  - {m}")

    print("--------------------------------------------------")

    for mount in mounts:

        print(f"\nScanning: {mount}")

        images = sorted(mount.glob("*.png"))

        if not images:
            print("  - No PNG files found")
            continue

        print(f"  - Found {len(images)} images")

        for path in images:
            p = multiprocessing.Process(target=process_image, args=(path,))
            p.start()
            p.join(IMAGE_TIMEOUT)

            if p.is_alive():
                print(f"  - TIMEOUT: {path}")
                p.terminate()
                p.join()
