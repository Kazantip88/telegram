from __future__ import annotations


def is_original_personal_message(message) -> bool:
    """Return True only for an original human-authored Telegram message."""
    if getattr(message, "post", False):
        return False
    if getattr(message, "fwd_from", None) is not None:
        return False
    if getattr(message, "via_bot_id", None) is not None:
        return False
    return True
