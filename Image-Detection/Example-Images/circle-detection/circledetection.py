from pathlib import Path
import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
image_folder = PROJECT_ROOT / "runtime-images"
output_folder = PROJECT_ROOT / "output"
output_folder.mkdir(parents=True, exist_ok=True)


image_files = []
for pattern in ("*.png",):
    image_files.extend(image_folder.glob(pattern))

image_files = sorted(image_files)

if not image_files:
    print(f"No images found in {image_folder}")

for image_path in image_files:
    print(f"Processing: {image_path.relative_to(PROJECT_ROOT)}")

    captured_frame = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)

    if captured_frame is None:
        print("  - Failed to load image, skipping")
        continue

    output_frame = captured_frame.copy()


    if captured_frame.shape[2] == 4:
        captured_frame_bgr = cv2.cvtColor(captured_frame, cv2.COLOR_BGRA2BGR)
    else:
        captured_frame_bgr = captured_frame

    # First blur to reduce noise prior to color space conversion
    captured_frame_bgr = cv2.medianBlur(captured_frame_bgr, 3)
    # Convert to Lab color space, we only need to check one channel (a-channel) for red here
    captured_frame_lab = cv2.cvtColor(captured_frame_bgr, cv2.COLOR_BGR2Lab)
    # Threshold the Lab image, keep only the red pixels
    # Possible yellow threshold: [20, 110, 170][255, 140, 215]
    # Possible blue threshold: [20, 115, 70][255, 145, 120]
    captured_frame_lab_red = cv2.inRange(captured_frame_lab, np.array([20, 150, 150]), np.array([190, 255, 255]))
    # Second blur to reduce more noise, easier circle detection
    captured_frame_lab_red = cv2.GaussianBlur(captured_frame_lab_red, (5, 5), 2, 2)
    # Use the Hough transform to detect circles in the image
    circles = cv2.HoughCircles(captured_frame_lab_red, cv2.HOUGH_GRADIENT, 1, captured_frame_lab_red.shape[0] / 8, param1=100, param2=18, minRadius=5, maxRadius=60)

    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        center_x, center_y, radius = circles[0, 0], circles[0, 1], circles[0, 2]
        cv2.circle(output_frame, center=(center_x, center_y), radius=radius, color=(0, 255, 0), thickness=2)
        print(f"  - Circle detected at ({center_x}, {center_y}) with radius {radius}")

        padding = int(round(radius * 0.2))
        x_min = max(center_x - radius - padding, 0)
        y_min = max(center_y - radius - padding, 0)
        x_max = min(center_x + radius + padding, captured_frame.shape[1] - 1)
        y_max = min(center_y + radius + padding, captured_frame.shape[0] - 1)

        cropped_frame = captured_frame[y_min : y_max + 1, x_min : x_max + 1]
        output_path = output_folder / f"{image_path.stem}_cropped.png"
        if not cv2.imwrite(str(output_path), cropped_frame):
            print(f"  - Failed to write cropped image to {output_path}")
        else:
            print(f"  - Saved cropped image to {output_path.relative_to(PROJECT_ROOT)}")
    else:
        print("  - No circles detected")

   
    window_name = f"frame - {image_path.name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(window_name, output_frame)
    cv2.waitKey(1)
    cv2.destroyWindow(window_name)


  