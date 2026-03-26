import os
import time
import glob
import struct
import argparse
import serial

MAGIC = b"\xE5\x32"
VERSION = 1

HDR_FMT = "<2sBBIIHH"
HDR_SIZE = struct.calcsize(HDR_FMT)

FLAG_LAST = 0x01


class PacketStreamParser:
    """
    Feed arbitrary bytes; pop complete packets: header + chunk_len bytes.
    Resyncs on MAGIC.
    """
    def __init__(self):
        self.buf = bytearray()

    def feed(self, b: bytes):
        if b:
            self.buf += b

    def pop_packet(self):
        while True:
            if len(self.buf) < 2:
                return None

            idx = self.buf.find(MAGIC)
            if idx == -1:
                # keep last byte in case it is start of magic
                self.buf = self.buf[-1:]
                return None

            if idx > 0:
                del self.buf[:idx]

            if len(self.buf) < HDR_SIZE:
                return None

            try:
                magic, ver, flags, image_id, total_size, seq, chunk_len = struct.unpack(
                    HDR_FMT, self.buf[:HDR_SIZE]
                )
            except struct.error:
                del self.buf[:2]
                continue

            if magic != MAGIC or ver != VERSION:
                del self.buf[:2]
                continue

            need = HDR_SIZE + chunk_len
            if len(self.buf) < need:
                return None

            pkt = bytes(self.buf[:need])
            del self.buf[:need]
            return pkt


class ImageReassembler:
    def __init__(self):
        self.state = {}

    def push_packet(self, pkt: bytes):
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
            st = {"total_size": total_size, "chunks": {}, "last_seq": None}
            self.state[image_id] = st

        if st["total_size"] != total_size:
            return None

        if seq not in st["chunks"]:
            st["chunks"][seq] = chunk

        if flags & FLAG_LAST:
            st["last_seq"] = seq

        last = st["last_seq"]
        if last is not None:
            for i in range(last + 1):
                if i not in st["chunks"]:
                    return None

            data = b"".join(st["chunks"][i] for i in range(last + 1))
            data = data[:total_size]

            if len(data) == total_size:
                del self.state[image_id]
                return image_id, data

        return None


def pick_port(explicit=None):
    if explicit:
        return explicit
    candidates = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if not candidates:
        raise RuntimeError("No serial device found. Plug in RX ESP32 and check /dev/ttyUSB* or /dev/ttyACM*.")
    return sorted(candidates)[0]


def guess_ext(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xFF\xD8\xFF"):
        return ".jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ".bin"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--baud", type=int, default=115200)
    # ap.add_argument("--outdir", default="C:\\Users\\Tyler\\Documents\\Codes\\Python\\SNR Design\\images")
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    OUTPUT_DIR = os.path.join(BASE_DIR, "output/encrypted")
    ap.add_argument("--outdir", default=OUTPUT_DIR)
    args = ap.parse_args()

    port = pick_port(args.port)
    os.makedirs(args.outdir, exist_ok=True)

    print("Using port:", port)
    ser = serial.Serial(port, args.baud, timeout=0.1)
    ser.reset_input_buffer()

    parser = PacketStreamParser()
    reasm = ImageReassembler()

    try:
        print("Listening for packets...")
        while True:
            b = ser.read(4096)
            if b:
                parser.feed(b)

            while True:
                pkt = parser.pop_packet()
                if pkt is None:
                    break

                res = reasm.push_packet(pkt)
                if res:
                    image_id, data = res
                    ext = guess_ext(data)
                    outpath = os.path.join(args.outdir, f"image_{image_id:08X}{ext}")
                    with open(outpath, "wb") as f:
                        f.write(data)
                    print(f"[OK] wrote {outpath} ({len(data)} bytes)")

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        ser.close()


if __name__ == "__main__":
    main()