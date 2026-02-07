"""Base bot interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from claw_claw.state import MarketContext, Proposal


class BaseBot(ABC):
    """Base class for strategy bots."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def propose(self, market: MarketContext) -> Optional[Proposal]:
        raise NotImplementedError
