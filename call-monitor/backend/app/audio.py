import logging

logger = logging.getLogger("audio_handler")


def validate_pcm_chunk(raw_bytes: bytes, expected_size: int) -> dict:
    """Validates a raw PCM 16-bit mono chunk against the size the sender declared."""
    actual_size = len(raw_bytes)
    if actual_size != expected_size:
        raise ValueError(
            f"Payload size mismatch: expected {expected_size} bytes, got {actual_size} bytes"
        )
    if actual_size % 2 != 0:
        raise ValueError(f"Odd byte length {actual_size} for 16-bit PCM data")

    return {"valid": True, "bytes": actual_size, "samples": actual_size // 2}
