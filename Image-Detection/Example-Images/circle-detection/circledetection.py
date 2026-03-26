from pathlib import Path
import time
import cv2
import numpy as np

# ===================== CONFIG =====================

STATIC_KEY = 123  # Static key for XOR encryption
PER_IMAGE_TIMEOUT_SEC = 5

# Slightly relaxed red segmentation in HSV (red wraps around hue boundaries)
RED_LOWER_1 = np.array([0, 100, 80], dtype=np.uint8)
RED_UPPER_1 = np.array([10, 255, 255], dtype=np.uint8)
RED_LOWER_2 = np.array([170, 100, 80], dtype=np.uint8)
RED_UPPER_2 = np.array([180, 255, 255], dtype=np.uint8)

# Require at least this fraction of red pixels inside detected circle
MIN_RED_RATIO_IN_CIRCLE = 0.55

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

# ===================== FOLDERS =====================

# INPUT → runtime-images
runtime_folder = PROJECT_ROOT / "mock-images"

# OUTPUT → output
output_folder = PROJECT_ROOT / "output"
output_folder.mkdir(parents=True, exist_ok=True)

# ENCRYPTED → output/encrypted
encrypted_folder = output_folder / "encrypted"
encrypted_folder.mkdir(parents=True, exist_ok=True)

# Get images from runtime-images
image_files = sorted(runtime_folder.glob("*.png"))

if not image_files:
    print(f"No images found in {runtime_folder}")
else:
    print(f"Found {len(image_files)} images in {runtime_folder}")

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


def is_timed_out(start_time: float) -> bool:
    return (time.perf_counter() - start_time) > PER_IMAGE_TIMEOUT_SEC


def build_red_mask(frame_bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    red_mask_1 = cv2.inRange(hsv, RED_LOWER_1, RED_UPPER_1)
    red_mask_2 = cv2.inRange(hsv, RED_LOWER_2, RED_UPPER_2)
    red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)

    kernel = np.ones((3, 3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
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

    print("Reading from:", runtime_folder)
    print("Saving cropped to:", output_folder)
    print("Saving encrypted to:", encrypted_folder)
    print("--------------------------------------------------")

    for image_path in image_files:
        image_start = time.perf_counter()

        print(f"Processing: {image_path.name}")

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

        circles = cv2.HoughCircles(
            mask,
            cv2.HOUGH_GRADIENT,
            1,
            mask.shape[0] / 5,
            param1=100,
            param2=23,
            minRadius=5,
            maxRadius=60
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

            print(f"  - Circle detected at ({center_x}, {center_y}) radius {radius}")

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

        # Optional display (can comment out if running headless)
        window_name = f"frame - {image_path.name}"
        cv2.imshow(window_name, output_frame)
        cv2.waitKey(1)
        cv2.destroyWindow(window_name)