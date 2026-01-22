import random
from Chunker import build_packets_from_file
from ImageReassembler import ImageReassembler

def simulate_one(path: str, shuffle: bool = False):
    # Build packets
    image_id, packets = build_packets_from_file(path)

    # Optional: test out-of-order delivery
    if shuffle:
        random.shuffle(packets)

    # Reassemble
    r = ImageReassembler()
    rebuilt = None

    for pkt in packets:
        out = r.push_packet(pkt)
        if out is not None:
            rebuilt_id, rebuilt_bytes = out
            rebuilt = (rebuilt_id, rebuilt_bytes)
            break

    if rebuilt is None:
        raise RuntimeError("Did not reconstruct image (missing packets? header mismatch?)")

    rebuilt_id, rebuilt_bytes = rebuilt

    # Verify against original file bytes
    with open(path, "rb") as f:
        original = f.read()

    if rebuilt_id != image_id:
        raise RuntimeError(f"Image ID mismatch: sent {image_id}, got {rebuilt_id}")

    if rebuilt_bytes != original:
        # Helpful debug: find first mismatch
        for i, (a, b) in enumerate(zip(rebuilt_bytes, original)):
            if a != b:
                raise RuntimeError(f"Byte mismatch at offset {i}: got {a}, expected {b}")
        raise RuntimeError("Length mismatch or trailing mismatch")

    # Write output for visual check
    with open("reconstructed.png", "wb") as f:
        f.write(rebuilt_bytes)

    print("PASS:", path, "packets:", len(packets), "bytes:", len(original), "shuffle:", shuffle)

if __name__ == "__main__":
    simulate_one("deathstar.png", shuffle=False)
    simulate_one("deathstar.png", shuffle=True)
