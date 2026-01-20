from pathlib import Path
import cv2
import numpy as np

# USE ARROW KEYS TO MOVE AROUND IN THE IMAGE WINDOW

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
image_folder = PROJECT_ROOT / "runtime-images"


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

    # If we have extracted a circle, draw an outline
    # We only need to detect one circle here, since there will only be one reference object
    if circles is not None:
        circles = np.round(circles[0, :]).astype("int")
        cv2.circle(output_frame, center=(circles[0, 0], circles[0, 1]), radius=circles[0, 2], color=(0, 255, 0), thickness=2)
        print(f"  - Circle detected at ({circles[0, 0]}, {circles[0, 1]}) with radius {circles[0, 2]}")
    else:
        print("  - No circles detected")

    # Show annotated image (one window per file) and wait for keypress to advance
    window_name = f"frame - {image_path.name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(window_name, output_frame)
    cv2.waitKey(0)
    cv2.destroyWindow(window_name)


  