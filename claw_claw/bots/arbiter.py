"""Select a proposal from multiple bots."""
from __future__ import annotations

from typing import List, Optional

from claw_claw.state import Proposal


class Arbiter:
    def __init__(self, min_confidence: float = 0.6, dominance_gap: float = 0.15) -> None:
        self.min_confidence = min_confidence
        self.dominance_gap = dominance_gap

    def select(self, proposals: List[Proposal]) -> Optional[Proposal]:
        if not proposals:
            return None

        proposals = sorted(proposals, key=lambda p: p.confidence, reverse=True)
        top = proposals[0]
        if top.confidence < self.min_confidence:
            return None

        opposing = [p for p in proposals if p.direction != top.direction]
        if opposing:
            if opposing[0].confidence + self.dominance_gap >= top.confidence:
                return None

        return top
