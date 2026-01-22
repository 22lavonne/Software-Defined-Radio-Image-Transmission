import struct
import random
from pathlib import Path

MAGIC = b"\xE5\x32"
VERSION = 1
MAX_DATA = 200  # safe ESP-NOW payload size

# Header: magic(2) ver(1) flags(1) image_id(4) total_size(4) seq(2) chunk_len(2)
HDR_FMT = "<2sBBIIHH"
HDR_SIZE = struct.calcsize(HDR_FMT)

def build_packets_for_images(*image_names, folder="."):
    """
    image_names: exactly 10 filenames (strings)
    folder: directory containing the images

    Returns:
        dict: image_name -> {
            'image_id': int,
            'total_size': int,
            'packets': [bytes, ...]
        }
    """
    if len(image_names) != 10:
        raise ValueError("Exactly 10 image names required")

    results = {}

    for name in image_names:
        path = Path(folder) / name
        if not path.exists():
            raise FileNotFoundError(path)

        with open(path, "rb") as f:
            img_bytes = f.read()

        total_size = len(img_bytes)
        image_id = random.getrandbits(32)

        packets = []
        seq = 0

        for offset in range(0, total_size, MAX_DATA):
            chunk = img_bytes[offset: offset + MAX_DATA]
            flags = 0x01 if (offset + len(chunk)) >= total_size else 0x00

            header = struct.pack(
                HDR_FMT,
                MAGIC,
                VERSION,
                flags,
                image_id,
                total_size,
                seq,
                len(chunk)
            )

            packets.append(header + chunk)
            seq += 1

        results[name] = {
            "image_id": image_id,
            "total_size": total_size,
            "packets": packets
        }

    return results
