from pathlib import Path
import cv2
import numpy as np

# ===================== CONFIG =====================

STATIC_KEY = 123  # XOR encryption key

# Adjusted paths for your environment
OUTPUT_BASE = Path("/home/ethanwoe/Software-Defined-Radio-Image-Transmission/output")
INPUT_BASE = Path("/home/ethanwoe/Software-Defined-Radio-Image-Transmission/mock-images")

output_folder = OUTPUT_BASE
output_folder.mkdir(parents=True, exist_ok=True)

encrypted_folder = output_folder / "encrypted"
encrypted_folder.mkdir(parents=True, exist_ok=True)

# ===================== RED DETECTION =====================

def get_red_mask(image):
    """
    Creates a high-sensitivity binary mask for red objects.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

    # Widened Hue and lowered Saturation/Value for better detection in real-world lighting
    lower_red1 = np.array([0, 200, 150], np.uint8)
    upper_red1 = np.array([5, 255, 255], np.uint8)
    
    lower_red2 = np.array([175, 200, 150], np.uint8)
    upper_red2 = np.array([180, 255, 255], np.uint8)

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    # Morphological operations to solidify the circle shape
    kernel = np.ones((7, 7), np.uint8)
    
    # Fill small holes inside the red area
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)
    
    # Expand the red area slightly to ensure a strong outer edge for the detector
    red_mask = cv2.dilate(red_mask, kernel, iterations=1)

    return red_mask

def detect_circles(red_mask):
  
    if red_mask is None or red_mask.size == 0:
        return []

    # Smooth the mask to remove jagged pixel edges
    blurred_mask = cv2.GaussianBlur(red_mask, (9, 9), 2)

    circles = cv2.HoughCircles(
        blurred_mask,
        cv2.HOUGH_GRADIENT,
        dp=1,               # 1:1 resolution for maximum precision
        minDist=blurred_mask.shape[0] // 4,
        param1=100,           # Strict edge gradient requirement
        param2=51,            # High accumulator threshold to avoid false positives
        minRadius=15,
        maxRadius=100
    )

    if circles is None:
        return []

    # Convert detected circles to integers for cropping/drawing
    circles = np.round(circles[0, :]).astype(int)
    return [tuple(map(int, c)) for c in circles]

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

# ===================== INPUT =====================

def get_input_images():
    if not INPUT_BASE.exists() or not INPUT_BASE.is_dir():
        return []
    
    patterns = ("*.png", "*.jpg", "*.jpeg")
    image_files = []
    for pattern in patterns:
        image_files.extend(INPUT_BASE.rglob(pattern))
    
    return sorted(image_files)

# ===================== MAIN =====================

if __name__ == "__main__":
    image_files = get_input_images()

    if not image_files:
        print(f"No images found in {INPUT_BASE}")
        exit()

    print(f"Reading images from: {INPUT_BASE}")
    print(f"Found {len(image_files)} images")
    print("--------------------------------------------------\n")

    for idx, image_path in enumerate(image_files, 1):
        print(f"{idx}/{len(image_files)}. Processing: {image_path}")

        image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            print("  - Failed to load image")
            continue

        # 1. Detect Red
        red_mask = get_red_mask(image)

        if cv2.countNonZero(red_mask) < 50:
            print("no red circle detected")
            continue

        # 2. Detect Circles directly from the mask
        circles = detect_circles(red_mask)

        if not circles:
            print("no red circle detected")
            continue

        # Pick the best circle (largest radius)
        x, y, r = max(circles, key=lambda c: c[2])
        print("red circle detected")

        # 3. Crop with safety bounds
        y_min, y_max = max(y - r, 0), min(y + r, image.shape[0])
        x_min, x_max = max(x - r, 0), min(x + r, image.shape[1])

        cropped = image[y_min:y_max, x_min:x_max]

        if cropped.size == 0:
            print("  - Empty crop, skipping")
            continue

        # 4. Save and Encrypt
        output_path = output_folder / f"{image_path.stem}_cropped.png"

        if cv2.imwrite(str(output_path), cropped):
            print(f"    -> Saved: {output_path}")
            encrypt_image(output_path)
        else:
            print("  - Failed to save image")

    print("\nDone.")