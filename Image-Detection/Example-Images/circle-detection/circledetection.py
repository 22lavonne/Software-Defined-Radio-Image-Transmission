from pathlib import Path
import cv2
import numpy as np

# ===================== CONFIG =====================

STATIC_KEY = 123  # Static key for XOR encryption

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

# ===================== MAIN =====================

if __name__ == "__main__":

    print("Reading from:", runtime_folder)
    print("Saving cropped to:", output_folder)
    print("Saving encrypted to:", encrypted_folder)
    print("--------------------------------------------------")

    for image_path in image_files:

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

        captured_frame_bgr = cv2.medianBlur(captured_frame_bgr, 3)
        captured_frame_lab = cv2.cvtColor(captured_frame_bgr, cv2.COLOR_BGR2Lab)

        mask = cv2.inRange(
            captured_frame_lab,
            np.array([20, 150, 150]),
            np.array([190, 255, 255])
        )

        mask = cv2.GaussianBlur(mask, (5, 5), 2, 2)

        circles = cv2.HoughCircles(
            mask,
            cv2.HOUGH_GRADIENT,
            1,
            mask.shape[0] / 8,
            param1=100,
            param2=18,
            minRadius=5,
            maxRadius=60
        )

        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            center_x, center_y, radius = circles[0]

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

        else:
            print("  - No circles detected")

        # Optional display (can comment out if running headless)
        window_name = f"frame - {image_path.name}"
        cv2.imshow(window_name, output_frame)
        cv2.waitKey(1)
        cv2.destroyWindow(window_name)