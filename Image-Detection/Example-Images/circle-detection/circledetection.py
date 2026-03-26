from pathlib import Path
import time
import signal
import cv2
import numpy as np

# ===================== CONFIG =====================

STATIC_KEY = 123  # Static key for XOR encryption
PER_IMAGE_TIMEOUT_SEC = 5
IMAGE_SKIP_INTERVAL = 2  # Process every Nth image (1 = process all)
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

# Stricter red segmentation in HSV (red wraps around hue boundaries)
RED_LOWER_1 = np.array([0, 140, 120], dtype=np.uint8)
RED_UPPER_1 = np.array([10, 255, 255], dtype=np.uint8)
RED_LOWER_2 = np.array([170, 140, 120], dtype=np.uint8)
RED_UPPER_2 = np.array([180, 255, 255], dtype=np.uint8)

# Require at least this fraction of red pixels inside detected circle (stricter)
MIN_RED_RATIO_IN_CIRCLE = 0.85

# Require at least this fraction of edge pixels around the detected circle
# (helps reject blobs that are not circular)
MIN_EDGE_RATIO_IN_RING = 0.50

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# ===================== FOLDERS =====================

# INPUT → runtime-images
runtime_folder = PROJECT_ROOT / "mock-images"

# OUTPUT → output
output_folder = PROJECT_ROOT / "output"
output_folder.mkdir(parents=True, exist_ok=True)

encrypted_folder = output_folder / "encrypted"
encrypted_folder.mkdir(parents=True, exist_ok=True)

# ===================== MOUNT DETECTION =====================

def get_mount_points():
    mount_points = []

    # /media/<user>/<drive>
    media_base = Path("/media")
    if media_base.exists():
        for user_dir in media_base.iterdir():
            if user_dir.is_dir():
                for drive_dir in user_dir.iterdir():
                    if drive_dir.is_dir():
                        mount_points.append(drive_dir)

    # /mnt/<drive>
    mnt_base = Path("/mnt")
    if mnt_base.exists():
        for path in mnt_base.iterdir():
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

        print(f"    -> Encrypted: {encrypted_path}")

    except Exception as e:
        print(f"Encryption error: {e}")


def is_timed_out(start_time: float) -> bool:
    return (time.perf_counter() - start_time) > PER_IMAGE_TIMEOUT_SEC


def _timeout_handler(signum, frame):
    raise TimeoutError("per-image processing timed out")


def edge_ratio_on_circle(edge_img: np.ndarray, center_x: int, center_y: int, radius: int, thickness: int = 3) -> float:
    """Compute ratio of edge pixels in a ring around the circle center/radius.

    edge_img should be a single-channel binary/edge image (nonzero counts as edge).
    """
    h, w = edge_img.shape[:2]
    ring_mask = np.zeros((h, w), dtype=np.uint8)
    inner_r = max(1, radius - thickness)
    outer_r = radius + thickness
    cv2.circle(ring_mask, (center_x, center_y), outer_r, 255, thickness=-1)
    cv2.circle(ring_mask, (center_x, center_y), inner_r, 0, thickness=-1)

    total_ring_pixels = cv2.countNonZero(ring_mask)
    if total_ring_pixels == 0:
        return 0.0

    edges_in_ring = cv2.bitwise_and(edge_img, edge_img, mask=ring_mask)
    edge_pixels = cv2.countNonZero(edges_in_ring)
    return edge_pixels / total_ring_pixels


def build_red_mask(frame_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    red_mask_1 = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1)
    red_mask_2 = cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
    red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)

    kernel = np.ones((5, 5), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    red_mask = cv2.GaussianBlur(red_mask, (5, 5), 1.5, 1.5)

    return red_mask


def red_ratio_inside_circle(mask: np.ndarray, center_x: int, center_y: int, radius: int) -> float:
    circle_mask = np.zeros(mask.shape[:2], dtype=np.uint8)
    cv2.circle(circle_mask, (center_x, center_y), radius, 255, thickness=-1)

    total_circle_pixels = cv2.countNonZero(circle_mask)
    if total_circle_pixels == 0:
        return 0.0

    red_inside = cv2.bitwise_and(mask, mask, mask=circle_mask)
    red_pixels = cv2.countNonZero(red_inside)
    return red_pixels / total_circle_pixels

# ===================== MAIN =====================

if __name__ == "__main__":

    mount_points = get_mount_points()

    if not mount_points:
        print("No mounted drives found.")
        exit()

    print("Mounted drives found:")
    for m in mount_points:
        print(f"  - {m}")

    print("--------------------------------------------------")
    for mount in mount_points:
        print(f"\nScanning root of: {mount}")

        image_files = sorted(
            p for p in mount.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_IMAGE_EXTS
        )

        if not image_files:
            print("  - No supported images found in root")
            continue

        print(f"  - Found {len(image_files)} images")

        for image_index, image_path in enumerate(image_files):
            if IMAGE_SKIP_INTERVAL > 1 and (image_index % IMAGE_SKIP_INTERVAL) != 0:
                print(f"  - Skipping image (interval={IMAGE_SKIP_INTERVAL}): {image_path.name}")
                continue

            image_start = time.perf_counter()

            # Install per-image timeout handler and arm the alarm
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(PER_IMAGE_TIMEOUT_SEC)

            print(f"\nProcessing: {image_path}")

            try:
                captured_frame = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

                if captured_frame is None:
                    print("  - Failed to load image, skipping")
                    continue

                output_frame = captured_frame.copy()

                # Handle grayscale safely
                if len(captured_frame.shape) == 2:
                    captured_frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_GRAY2BGR)
                elif captured_frame.shape[2] == 4:
                    captured_frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_BGRA2BGR)
                else:
                    captured_frame_bgr = captured_frame

                if is_timed_out(image_start):
                    print(f"  - Timed out after {PER_IMAGE_TIMEOUT_SEC:.1f}s, skipping")
                    continue

                captured_frame_bgr = cv2.medianBlur(captured_frame_bgr, 3)
                mask = build_red_mask(captured_frame_bgr)

                if is_timed_out(image_start):
                    print(f"  - Timed out after {PER_IMAGE_TIMEOUT_SEC:.1f}s, skipping")
                    continue

                # Stricter HoughCircles parameters to reduce false positives
                circles = cv2.HoughCircles(
                    mask,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=mask.shape[0] / 4,
                    param1=120,
                    param2=38,
                    minRadius=12,
                    maxRadius=45
                )

                if is_timed_out(image_start):
                    print(f"  - Timed out after {PER_IMAGE_TIMEOUT_SEC:.1f}s, skipping")
                    continue

                if circles is not None:
                    circles = np.round(circles[0, :]).astype("int")
                    center_x, center_y, radius = max(circles, key=lambda c: c[2])

                    red_ratio = red_ratio_inside_circle(mask, center_x, center_y, radius)
                    if red_ratio < MIN_RED_RATIO_IN_CIRCLE:
                        print(
                            f"  - Rejected circle at ({center_x}, {center_y}) radius {radius}; "
                            f"red ratio {red_ratio:.2f} < {MIN_RED_RATIO_IN_CIRCLE:.2f}"
                        )
                        continue

                    # Compute edges and ensure a reasonable fraction lies on the circle ring
                    gray = cv2.cvtColor(captured_frame_bgr, cv2.COLOR_BGR2GRAY)
                    gray = cv2.GaussianBlur(gray, (5, 5), 1.5)
                    edges = cv2.Canny(gray, 50, 150)

                    edge_ratio = edge_ratio_on_circle(edges, center_x, center_y, radius, thickness=3)
                    if edge_ratio < MIN_EDGE_RATIO_IN_RING:
                        print(
                            f"  - Rejected circle at ({center_x}, {center_y}) radius {radius}; "
                            f"edge ratio {edge_ratio:.2f} < {MIN_EDGE_RATIO_IN_RING:.2f}"
                        )
                        continue

                    print(f"  - Circle detected at ({center_x}, {center_y}) radius {radius} (red {red_ratio:.2f}, edge {edge_ratio:.2f})")

                    padding = int(round(radius * 0.2))

                    x_min = max(center_x - radius - padding, 0)
                    y_min = max(center_y - radius - padding, 0)
                    x_max = min(center_x + radius + padding, captured_frame.shape[1] - 1)
                    y_max = min(center_y + radius + padding, captured_frame.shape[0] - 1)

                    cropped_frame = captured_frame[y_min:y_max + 1, x_min:x_max + 1]

                    if cropped_frame.size == 0:
                        print("  - WARNING: Cropped region empty")
                        continue

                    output_path = output_folder / f"{image_path.stem}_cropped.png"

                    if cv2.imwrite(str(output_path), cropped_frame):
                        print(f"  - Saved cropped image to {output_path}")
                        encrypt_image(output_path)
                    else:
                        print("  - Failed to write cropped image")

                    if is_timed_out(image_start):
                        print(f"  - Timed out after {PER_IMAGE_TIMEOUT_SEC:.1f}s (after save/encrypt)")

                else:
                    print("  - No circles detected")

            except TimeoutError:
                print(f"  - TIMED OUT: image exceeded {PER_IMAGE_TIMEOUT_SEC} seconds, skipping")
                continue
            finally:
                # Disarm the alarm for this image
                try:
                    signal.alarm(0)
                except Exception:
                    pass

            # Optional display (can comment out if running headless)
            window_name = f"frame - {image_path.name}"
            cv2.imshow(window_name, output_frame)
            cv2.waitKey(1)
            cv2.destroyWindow(window_name)
