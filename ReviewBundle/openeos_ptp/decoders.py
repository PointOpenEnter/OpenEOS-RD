"""
Offline decoders for Canon EOS R6 Mark II diagnostic properties.
Decodes 0x12000001, 0x12000003, and 0x12000005 based on р62.pcapng wire evidence.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass


class DecoderError(Exception):
    """Base exception for all decoder errors."""
    pass


class PayloadLengthError(DecoderError):
    """Raised when the received payload length does not match the expected length."""
    def __init__(self, property_id: int, expected: int, actual: int):
        super().__init__(
            f"Invalid payload length for Property 0x{property_id:08X}: "
            f"expected {expected} bytes, received {actual} bytes."
        )
        self.property_id = property_id
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class ShutterCounterResult:
    """
    Decoded result for Property 0x12000001 (Shutter Counter).
    Neutral naming retained per specification; does not assert mechanical-only actuation.
    Per OPENEOS_ONLINE_READ_SPEC_V1.2, Property 0x12000001 is a general shutter counter
    and is NOT proven to correspond exclusively to mechanical shutter actuations.
    """
    shutter_counter: int
    opaque_tail: bytes
    raw_payload: bytes
    status: str = "VERIFIED"

    @property
    def mechanical_shutter_counter(self) -> int:
        """
        DEPRECATED: Historical alias for shutter_counter.
        Retained strictly for backward compatibility.
        Property 0x12000001 represents a general shutter counter and is NOT
        proven to correspond exclusively to mechanical shutter actuations.
        Use 'shutter_counter' instead.
        """
        import warnings
        warnings.warn(
            "mechanical_shutter_counter is deprecated; use shutter_counter. "
            "Property 0x12000001 is a general shutter counter with unproven mechanical-only semantics.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.shutter_counter

    def __str__(self) -> str:
        return (
            f"ShutterCounterResult(shutter_counter={self.shutter_counter:,}, "
            f"opaque_tail={self.opaque_tail.hex()}, status={self.status})"
        )


@dataclass(frozen=True)
class ReleaseCounterResult:
    """
    Decoded result for Property 0x12000003 (Release Counter Total).
    """
    release_counter_total: int
    raw_payload: bytes
    status: str = "VERIFIED"

    def __str__(self) -> str:
        return (
            f"ReleaseCounterResult(total={self.release_counter_total:,}, "
            f"status={self.status})"
        )


@dataclass(frozen=True)
class PowerAndUptimeResult:
    """
    Decoded result for Property 0x12000005 (Power On Count & Operating Time).
    """
    power_on_count: int
    operating_time_seconds: int
    operating_time_formatted: str
    raw_payload: bytes
    status: str = "VERIFIED"

    def __str__(self) -> str:
        return (
            f"PowerAndUptimeResult(power_on={self.power_on_count:,}, "
            f"uptime={self.operating_time_formatted} ({self.operating_time_seconds:,} s), "
            f"status={self.status})"
        )


def format_uptime(total_seconds: int) -> str:
    """
    Formats total seconds into Canon service diagnostic format: 'XXd YYh ZZm Ws'.
    """
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days:02d}d {hours:02d}h {minutes:02d}m {seconds:02d}s"


def decode_shutter_counter(data: bytes) -> ShutterCounterResult:
    """
    Decodes the 8-byte payload of Property 0x12000001 (TxID 26 Bulk IN).
    
    Layout:
      - 0..3: uint32 LE Shutter Counter (e.g. 0x0000ED11 = 60,689)
              Neutral semantics: general shutter counter (not proven mechanical-only).
      - 4..7: uint32 LE opaque tail / reserved bytes (must be preserved in full)
    """
    if not isinstance(data, (bytes, bytearray)):
        raise DecoderError(f"Expected bytes or bytearray, got {type(data).__name__}")
    if len(data) != 8:
        raise PayloadLengthError(0x12000001, expected=8, actual=len(data))

    counter = struct.unpack("<I", data[0:4])[0]
    tail = bytes(data[4:8])

    return ShutterCounterResult(
        shutter_counter=counter,
        opaque_tail=tail,
        raw_payload=bytes(data),
    )


def decode_release_counter(data: bytes) -> ReleaseCounterResult:
    """
    Decodes the 4-byte payload of Property 0x12000003 (TxID 32 Bulk IN).
    
    Layout:
      - 0..3: uint32 LE Release Counter Total (e.g. 0x000CD2B9 = 840,377)
    """
    if not isinstance(data, (bytes, bytearray)):
        raise DecoderError(f"Expected bytes or bytearray, got {type(data).__name__}")
    if len(data) != 4:
        raise PayloadLengthError(0x12000003, expected=4, actual=len(data))

    total = struct.unpack("<I", data[0:4])[0]

    return ReleaseCounterResult(
        release_counter_total=total,
        raw_payload=bytes(data),
    )


def decode_power_and_uptime(data: bytes) -> PowerAndUptimeResult:
    """
    Decodes the 8-byte payload of Property 0x12000005 (TxID 63 Bulk IN).
    
    Layout:
      - 0..3: uint32 LE Power On Count (e.g. 0x00001760 = 5,984)
      - 4..7: uint32 LE Total Operating Time in seconds (e.g. 0x0033C207 = 3,392,007 s)
    """
    if not isinstance(data, (bytes, bytearray)):
        raise DecoderError(f"Expected bytes or bytearray, got {type(data).__name__}")
    if len(data) != 8:
        raise PayloadLengthError(0x12000005, expected=8, actual=len(data))

    power_on, uptime_sec = struct.unpack("<II", data[0:8])
    formatted = format_uptime(uptime_sec)

    return PowerAndUptimeResult(
        power_on_count=power_on,
        operating_time_seconds=uptime_sec,
        operating_time_formatted=formatted,
        raw_payload=bytes(data),
    )
