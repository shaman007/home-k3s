"""Bounded mono Opus transport: 24 kHz, 20 ms frames, 24 kbit/s CBR.

Each WebSocket binary message contains big-endian uint16 packet lengths followed
by raw Opus packets. This is an internal negotiated format, not an Ogg file.
"""

import ctypes
import struct
from functools import lru_cache

RATE = 24000
SAMPLES = 480
FRAME_BYTES = SAMPLES * 2
MAX_PACKET = 1275


@lru_cache(maxsize=1)
def _library():
    """Bind fixed native signatures; only encoder_ctl has variadic arguments."""
    lib = ctypes.CDLL("libopus.so.0")
    pointer, integer = ctypes.c_void_p, ctypes.c_int
    sample_pointer = ctypes.POINTER(ctypes.c_int16)
    signatures = {
        "opus_encoder_create": ([integer, integer, integer, ctypes.POINTER(integer)], pointer),
        "opus_decoder_create": ([integer, integer, ctypes.POINTER(integer)], pointer),
        "opus_encoder_destroy": ([pointer], None),
        "opus_decoder_destroy": ([pointer], None),
        "opus_encoder_ctl": ([pointer, integer], integer),
        "opus_decoder_ctl": ([pointer, integer], integer),
        "opus_encode": ([pointer, sample_pointer, integer, pointer, integer], integer),
        "opus_decode": ([pointer, pointer, integer, sample_pointer, integer, integer], integer),
    }
    for name, (arguments, result) in signatures.items():
        function = getattr(lib, name)
        function.argtypes, function.restype = arguments, result
    return lib


def _check(result):
    """Expose native errors without logging any audio data."""
    if result < 0:
        raise ValueError(f"Opus codec error {result}")
    return result


class OpusEncoder:
    """Keep framing and encoder state across chunks within one spoken turn."""

    def __init__(self):
        self.lib = _library()
        error = ctypes.c_int()
        self.handle = self.lib.opus_encoder_create(RATE, 1, 2048, ctypes.byref(error))
        _check(error.value)
        self.pending = bytearray()
        self.active = False
        # CBR gives predictable traffic; 24 kbit/s is 60 bytes per 20 ms.
        _check(self.lib.opus_encoder_ctl(self.handle, 4002, ctypes.c_int(24000)))
        _check(self.lib.opus_encoder_ctl(self.handle, 4006, ctypes.c_int(0)))

    def reset(self):
        """Reset between turns without carrying prediction or pending samples."""
        self.pending.clear()
        self.active = False
        _check(self.lib.opus_encoder_ctl(self.handle, 4028))

    def feed(self, pcm):
        """Encode complete 20 ms frames, retaining a bounded incomplete tail."""
        if len(pcm) % 2:
            raise ValueError("Unaligned PCM16")
        self.active = self.active or bool(pcm)
        self.pending.extend(pcm)
        output = bytearray()
        count = len(self.pending) // FRAME_BYTES
        for offset in range(0, count * FRAME_BYTES, FRAME_BYTES):
            samples = (ctypes.c_int16 * SAMPLES).from_buffer_copy(
                self.pending[offset:offset + FRAME_BYTES]
            )
            packet = ctypes.create_string_buffer(MAX_PACKET)
            size = _check(self.lib.opus_encode(self.handle, samples, SAMPLES, packet, MAX_PACKET))
            output.extend(struct.pack("!H", size))
            output.extend(packet.raw[:size])
        del self.pending[:count * FRAME_BYTES]
        return bytes(output)

    def finish(self):
        """Pad the tail and flush codec lookahead so the final phoneme survives."""
        if not self.active:
            return b""
        padding = (-len(self.pending)) % FRAME_BYTES
        result = self.feed(bytes(padding + FRAME_BYTES))
        self.active = False
        return result

    def close(self):
        """Release the native encoder exactly once."""
        if self.handle:
            self.lib.opus_encoder_destroy(self.handle)
            self.handle = None


class OpusDecoder:
    """Decode validated length-prefixed packets directly into playback PCM."""

    def __init__(self):
        self.lib = _library()
        error = ctypes.c_int()
        self.handle = self.lib.opus_decoder_create(RATE, 1, ctypes.byref(error))
        _check(error.value)

    def decode(self, wire):
        """Reject truncated/oversized framing and anything except 20 ms frames."""
        if not wire or len(wire) > 65536:
            raise ValueError("Invalid Opus message size")
        output, offset = bytearray(), 0
        while offset < len(wire):
            if len(wire) - offset < 2 or len(output) >= RATE * 2 * 5:
                raise ValueError("Invalid Opus framing")
            size = struct.unpack_from("!H", wire, offset)[0]
            offset += 2
            if not 1 <= size <= MAX_PACKET or offset + size > len(wire):
                raise ValueError("Invalid Opus packet length")
            packet = ctypes.create_string_buffer(wire[offset:offset + size])
            samples = (ctypes.c_int16 * SAMPLES)()
            count = _check(self.lib.opus_decode(self.handle, packet, size, samples, SAMPLES, 0))
            if count != SAMPLES:
                raise ValueError("Unexpected Opus frame duration")
            output.extend(bytes(samples))
            offset += size
        return bytes(output)

    def reset(self):
        """Match the encoder prediction reset at each new turn."""
        _check(self.lib.opus_decoder_ctl(self.handle, 4028))

    def close(self):
        """Release the native decoder exactly once."""
        if self.handle:
            self.lib.opus_decoder_destroy(self.handle)
            self.handle = None
