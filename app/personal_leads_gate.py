from __future__ import annotations


def is_original_personal_message(message) -> bool:
    """Allow only original human-authored Telegram messages."""
    return not any((
        getattr(message, "post", False),
        getattr(message, "fwd_from", None) is not None,
        getattr(message, "via_bot_id", None) is not None,
    ))
