import struct

MAGIC = b"\xE5\x32"
VERSION = 1

HDR_FMT = "<2sBBIIHH"   # magic, ver, flags, image_id, total_size, seq, chunk_len
HDR_SIZE = struct.calcsize(HDR_FMT)

class ImageReassembler:
    def __init__(self):
        # image_id -> state
        self.state = {}

    def push_packet(self, pkt: bytes):
        """Feed one packet. Returns (image_id, png_bytes) when an image completes, else None."""
        if len(pkt) < HDR_SIZE:
            return None

        magic, ver, flags, image_id, total_size, seq, chunk_len = struct.unpack(
            HDR_FMT, pkt[:HDR_SIZE]
        )

        if magic != MAGIC or ver != VERSION:
            return None

        chunk = pkt[HDR_SIZE:HDR_SIZE + chunk_len]
        if len(chunk) != chunk_len:
            return None

        st = self.state.get(image_id)
        if st is None:
            st = {
                "total_size": total_size,
                "chunks": {},      # seq -> bytes
                "last_seq": None
            }
            self.state[image_id] = st

        # Basic sanity
        if st["total_size"] != total_size:
            return None

        # Store chunk if new
        if seq not in st["chunks"]:
            st["chunks"][seq] = chunk

        # Mark last chunk seq if flagged
        if flags & 0x01:
            st["last_seq"] = seq

        # If we know the last seq, check if we have everything 0..last_seq
        last = st["last_seq"]
        if last is not None:
            for i in range(last + 1):
                if i not in st["chunks"]:
                    return None

            # Rebuild in order
            data = b"".join(st["chunks"][i] for i in range(last + 1))
            data = data[:total_size]  # trim if needed

            if len(data) == total_size and data[:8] == b"\x89PNG\r\n\x1a\n":
                # Done — remove state and return
                del self.state[image_id]
                return image_id, data

        return None
