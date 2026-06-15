"""MVP3 P3-cit — the citizen civic card.

Answers the one question nothing else in PRISM answers: "what about *my*
barrio?" Given a barrio, aggregates the model outputs that already exist
(serving substation, downstream consequence, community resilience, road
access, flood exposure, planned investments) into one plain-language card,
every figure labeled with its confidence tier.
"""
from __future__ import annotations

from prism.citizen.card import get_civic_card, list_barrios

__all__ = ["get_civic_card", "list_barrios"]
