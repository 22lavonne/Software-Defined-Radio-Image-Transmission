import struct
import random

MAGIC = b"\xE5\x32"
VERSION = 1
MAX_DATA = 200  # safe payload

# magic(2) ver(1) flags(1) image_id(4) total_size(4) seq(2) chunk_len(2)
HDR_FMT = "<2sBBIIHH"
HDR_SIZE = struct.calcsize(HDR_FMT)

def build_packets_from_bytes(data: bytes, image_id: int | None = None, max_data: int = MAX_DATA):
    """Return (image_id, packets:list[bytes]) for one binary blob."""
    total_size = len(data)
    if image_id is None:
        image_id = random.getrandbits(32)

    packets = []
    seq = 0

    for offset in range(0, total_size, max_data):
        chunk = data[offset: offset + max_data]
        flags = 0x01 if (offset + len(chunk)) >= total_size else 0x00

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

def build_packets_from_file(path: str, image_id: int | None = None, max_data: int = MAX_DATA):
    with open(path, "rb") as f:
        data = f.read()
    return build_packets_from_bytes(data, image_id=image_id, max_data=max_data)
