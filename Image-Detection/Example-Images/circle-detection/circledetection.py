from pathlib import Path
import cv2
import numpy as np

# ===================== CONFIG =====================

STATIC_KEY = 123  # XOR encryption key

# Set your desired output location here
OUTPUT_BASE = Path("/home/ras1/Desktop/2026Project/transmission/output")

output_folder = OUTPUT_BASE
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
        print(f"    -> Encryption error: {e}")

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

        print(f"\nScanning: {mount}")

        # RECURSIVE search
        image_files = sorted(mount.rglob("*.png"))

        if not image_files:
            print("  - No PNG images found")
            continue

        print(f"  - Found {len(image_files)} images")

        for image_path in image_files:

            print(f"\nProcessing: {image_path}")

            captured_frame = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

            if captured_frame is None:
                print("  - Failed to load image")
                continue

            # Normalize to BGR
            if len(captured_frame.shape) == 2:
                frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_GRAY2BGR)
            elif captured_frame.shape[2] == 4:
                frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_BGRA2BGR)
            else:
                frame_bgr = captured_frame

            frame_bgr = cv2.medianBlur(frame_bgr, 3)
            frame_lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2Lab)

            mask = cv2.inRange(
                frame_lab,
                np.array([20, 150, 150]),
                np.array([190, 255, 255])
            )

            mask = cv2.GaussianBlur(mask, (5, 5), 2, 2)

            circles = cv2.HoughCircles(
                mask,
                cv2.HOUGH_GRADIENT,
                dp=1,
                minDist=mask.shape[0] / 8,
                param1=100,
                param2=18,
                minRadius=5,
                maxRadius=60
            )

            if circles is None:
                print("  - No circles detected")
                continue

            circles = np.round(circles[0, :]).astype("int")
            cx, cy, r = circles[0]

            print(f"  - Circle at ({cx}, {cy}), r={r}")

            padding = int(r * 0.2)

            x_min = max(cx - r - padding, 0)
            y_min = max(cy - r - padding, 0)
            x_max = min(cx + r + padding, captured_frame.shape[1] - 1)
            y_max = min(cy + r + padding, captured_frame.shape[0] - 1)

            cropped = captured_frame[y_min:y_max + 1, x_min:x_max + 1]

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

