from __future__ import annotations

from dataclasses import dataclass
from .detector import Signals

@dataclass(frozen=True)
class Score:
    total: int
    priority: str
    reasons: tuple[str, ...]


def score_lead(signals: Signals) -> Score:
    points = 0
    reasons: list[str] = []
    if signals.has_loss:
        points += 20; reasons.append("reported loss")
    if signals.amounts:
        points += 15; reasons.append("amount specified")
        if max(signals.amounts) >= 5000:
            points += 20; reasons.append("loss >= EUR 5,000")
    if signals.matched.get("investment"):
        points += 10; reasons.append("investment context")
    if signals.has_withdrawal:
        points += 20; reasons.append("withdrawal blocked")
    if signals.matched.get("support"):
        points += 10; reasons.append("support unavailable")
    if signals.has_evidence:
        points += 15; reasons.append("evidence mentioned")
    if signals.has_fraud:
        points += 15; reasons.append("fraud suspected")
    if signals.matched.get("help"):
        points += 20; reasons.append("seeking recovery/legal help")

    # Strong negative signals keep informational/speculative messages out.
    text_hits = signals.matched
    if not signals.has_loss and not signals.has_withdrawal and not signals.has_fraud:
        if signals.matched.get("investment"):
            points -= 30; reasons.append("investment question without loss")

    points = max(0, min(points, 100))
    if points >= 80:
        priority = "HOT"
    elif points >= 50:
        priority = "NORMAL"
    else:
        priority = "IGNORE"
    return Score(points, priority, tuple(reasons))
