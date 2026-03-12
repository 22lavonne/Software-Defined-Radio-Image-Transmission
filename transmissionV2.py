"""
uart_image_sender.py

- Keeps your existing CLI behavior
- Adds a clean callable function: transmit_folder(...)
- Also adds transmit_folder_with_serial(...) if you want to reuse an already-open Serial port
"""

import os
import time
import glob
import struct
import random
import argparse
from typing import Optional, List, Tuple, Dict, Any

import serial

# ---------------- Your protocol (unchanged) ----------------
MAGIC = b"\xE5\x32"
VERSION = 1
MAX_DATA_DEFAULT = 200  # safe payload size

# magic(2) ver(1) flags(1) image_id(4) total_size(4) seq(2) chunk_len(2)
HDR_FMT = "<2sBBIIHH"
HDR_SIZE = struct.calcsize(HDR_FMT)

FLAG_LAST = 0x01


def build_packets_from_bytes(
    data: bytes,
    image_id: Optional[int] = None,
    max_data: int = MAX_DATA_DEFAULT,
):
    total_size = len(data)
    if image_id is None:
        image_id = random.getrandbits(32)

    packets = []
    seq = 0

    for offset in range(0, total_size, max_data):
        chunk = data[offset: offset + max_data]
        flags = FLAG_LAST if (offset + len(chunk)) >= total_size else 0x00

        header = struct.pack(
            HDR_FMT,
            MAGIC,
            VERSION,
            flags,
            image_id,
            total_size,
            seq,
            len(chunk),
        )
        packets.append(header + chunk)
        seq += 1

    return image_id, packets


def build_packets_from_file(
    path: str,
    image_id: Optional[int] = None,
    max_data: int = MAX_DATA_DEFAULT,
):
    with open(path, "rb") as f:
        data = f.read()
    return build_packets_from_bytes(data, image_id=image_id, max_data=max_data)


# ---------------- Serial helpers ----------------
def pick_port(explicit: Optional[str] = None) -> str:
    """
    If explicit is provided (e.g., 'COM7' on Windows or '/dev/ttyUSB0' on Linux),
    returns it. Otherwise, auto-picks from Linux-style device names.

    Note: on Windows, pass --port COMx (recommended).
    """
    if explicit:
        return explicit

    candidates = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if not candidates:
        raise RuntimeError(
            "No ESP32 serial device found.\n"
            "Linux: check /dev/ttyUSB* or /dev/ttyACM*\n"
            "Windows: pass --port COMx (e.g., --port COM7)"
        )
    return sorted(candidates)[0]


def list_images(folder: str) -> List[str]:
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".bin")
    files = []
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(exts):
            files.append(os.path.join(folder, name))
    return files


def wait_for_line(ser: serial.Serial, timeout_s: float) -> Optional[str]:
    """Read lines until timeout; return first non-empty line or None."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        line = ser.readline()
        if not line:
            continue
        try:
            s = line.decode("utf-8", errors="ignore").strip()
        except Exception:
            s = ""
        if s:
            return s
    return None


# ---------------- Main send logic (unchanged behavior) ----------------
def send_one_image(
    ser: serial.Serial,
    path: str,
    max_data: int,
    cache_bin_dir: Optional[str],
    per_image_good_timeout: float,
    inter_packet_delay: float,
    verbose: bool = True,
) -> Tuple[int, int, int]:
    """
    Returns (image_id, total_size, num_packets)
    """
    # Optional caching: store raw bytes as .bin (NOT text)
    if cache_bin_dir:
        os.makedirs(cache_bin_dir, exist_ok=True)
        with open(path, "rb") as f:
            data = f.read()
        base = os.path.basename(path)
        out_bin = os.path.join(cache_bin_dir, base + ".bin")
        with open(out_bin, "wb") as f:
            f.write(data)
        image_id, packets = build_packets_from_bytes(data, max_data=max_data)
    else:
        image_id, packets = build_packets_from_file(path, max_data=max_data)

    # Pull total_size from first header (for logging)
    _, _, _, _, total_size, _, _ = struct.unpack(HDR_FMT, packets[0][:HDR_SIZE])

    if verbose:
        print(
            f"\n[SEND] {os.path.basename(path)}  bytes={total_size}  "
            f"packets={len(packets)}  image_id=0x{image_id:08X}"
        )

    # Send packets raw (binary)
    for i, pkt in enumerate(packets):
        ser.write(pkt)
        if inter_packet_delay > 0:
            time.sleep(inter_packet_delay)

        if verbose and ((i + 1) % 20 == 0 or (i + 1) == len(packets)):
            print(f"  -> sent {i+1}/{len(packets)} packets")

    # Wait for ESP32 to say the wireless transfer was good
    t0 = time.time()
    while time.time() - t0 < per_image_good_timeout:
        line = wait_for_line(ser, timeout_s=0.25)
        if not line:
            continue

        if verbose:
            print("[ESP32]", line)

        if line.strip() == "GOOD":
            return image_id, total_size, len(packets)

        if line.startswith("IMG_OK"):
            # Accept any IMG_OK as "good enough"
            return image_id, total_size, len(packets)

        if line.startswith("FAIL") or line.startswith("IMG_FAIL"):
            raise RuntimeError(f"ESP32 reported failure for image_id=0x{image_id:08X}: {line}")

    raise TimeoutError(f"Timed out waiting for GOOD/IMG_OK for image_id=0x{image_id:08X}")


# ---------------- NEW: callable functions ----------------
def transmit_folder_with_serial(
    ser: serial.Serial,
    folder: str,
    max_data: int = MAX_DATA_DEFAULT,
    cache_bin_dir: Optional[str] = None,
    good_timeout: float = 15.0,
    delay: float = 0.0,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Use this if you want to open the serial port elsewhere and reuse it.

    Returns a list of dict results, one per file:
      {"file": ..., "image_id": ..., "bytes": ..., "packets": ...}
    """
    images = list_images(folder)
    if not images:
        raise RuntimeError(f"No image files found in {folder}")

    results: List[Dict[str, Any]] = []

    if verbose:
        print(f"Found {len(images)} files")

    for idx, path in enumerate(images, start=1):
        if verbose:
            print(f"\n=== Image {idx}/{len(images)} ===")

        image_id, total_size, num_packets = send_one_image(
            ser=ser,
            path=path,
            max_data=max_data,
            cache_bin_dir=cache_bin_dir,
            per_image_good_timeout=good_timeout,
            inter_packet_delay=delay,
            verbose=verbose,
        )

        results.append(
            {
                "file": path,
                "image_id": image_id,
                "bytes": total_size,
                "packets": num_packets,
            }
        )

    # Optional: tell ESP32 we're done
    ser.write(b"ALL_DONE\n")
    ser.flush()

    if verbose:
        print("\n[DONE] All images sent and confirmed GOOD.")

    return results


def transmit_folder(
    folder: str,
    port: Optional[str] = None,
    baud: int = 115200,
    max_data: int = MAX_DATA_DEFAULT,
    cache_bin_dir: Optional[str] = None,
    good_timeout: float = 15.0,
    delay: float = 0.0,
    verbose: bool = True,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper: opens/closes Serial internally.

    Returns list of dict results, one per file.
    """
    port = pick_port(port)
    if verbose:
        print("Using port:", port)

    ser = serial.Serial(port, baud, timeout=0.2)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    try:
        return transmit_folder_with_serial(
            ser=ser,
            folder=folder,
            max_data=max_data,
            cache_bin_dir=cache_bin_dir,
            good_timeout=good_timeout,
            delay=delay,
            verbose=verbose,
        )
    finally:
        ser.close()


# ---------------- CLI entrypoint (still works like before) ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="Folder containing images to send (e.g., ./images)")
    ap.add_argument("--port", default=None, help="Serial port (Windows: COM7, Linux: /dev/ttyUSB0)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--max-data", type=int, default=MAX_DATA_DEFAULT,
                    help="Payload bytes per packet (must match ESP32 assumptions)")
    ap.add_argument("--cache-bin-dir", default=None,
                    help="Optional folder to write cached .bin copies (raw bytes).")
    ap.add_argument("--good-timeout", type=float, default=15.0,
                    help="Seconds to wait for ESP32 GOOD per image")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="Delay between packets (seconds). Start at 0.0")
    args = ap.parse_args()

    transmit_folder(
        folder=args.folder,
        port=args.port,
        baud=args.baud,
        max_data=args.max_data,
        cache_bin_dir=args.cache_bin_dir,
        good_timeout=args.good_timeout,
        delay=args.delay,
        verbose=True,
    )


if __name__ == "__main__":
    main()
