"""Serial frame reader for the Oculius RX board."""
import struct
import numpy as np
import serial

SYNC = b"\xA5\x5A"


class Frame:
    __slots__ = ("type", "ts", "rssi", "ch", "sig", "csi", "red", "ir")


def parse_csi(raw: bytes) -> np.ndarray:
    """int8 I/Q pairs -> complex subcarrier vector. ESP32 CSI order is [imag, real]."""
    a = np.frombuffer(raw[: len(raw) // 2 * 2], dtype=np.int8).astype(np.float32)
    return a[1::2] + 1j * a[0::2]


def frames(port="COM3", baud=921600):
    ser = serial.Serial(port, baud, timeout=0.2)
    buf = bytearray()
    while True:
        buf += ser.read(max(1, ser.in_waiting))
        while True:
            i = buf.find(SYNC)
            if i < 0:
                del buf[:-1]
                break
            if len(buf) < i + 5:
                del buf[:i]
                break
            t = buf[i + 2]
            n = buf[i + 3] | buf[i + 4] << 8
            if n > 1000:
                del buf[: i + 2]
                continue
            end = i + 5 + n + 1
            if len(buf) < end:
                del buf[:i]
                break
            body = bytes(buf[i + 5 : i + 5 + n])
            x = t ^ buf[i + 3] ^ buf[i + 4]
            for b in body:
                x ^= b
            if x != buf[end - 1]:
                del buf[: i + 2]
                continue
            del buf[:end]
            f = Frame()
            f.type = t
            if t == 1 and n > 7:
                f.ts, f.rssi, f.ch, f.sig = struct.unpack("<IbBB", body[:7])
                f.csi = parse_csi(body[7:])
            elif t == 2 and n == 12:
                f.ts, f.red, f.ir = struct.unpack("<III", body)
            else:
                continue
            yield f
