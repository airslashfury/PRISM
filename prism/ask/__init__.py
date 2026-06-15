"""Ask PRISM (MVP3 P3-shared) — natural-language query bar over read-only typed tools.

Haiku routes a question to one of `prism.ask.tools`'s typed, read-only model
queries; Sonnet composes the answer, citing the confidence tier(s) of
whatever the tool read (`prism.provenance`). Serves all three audiences and
never invents a number — lands after P1/P2/P3-cit so every answer is honest.
"""
from __future__ import annotations

from prism.ask.agent import AskResult, answer_query

__all__ = ["AskResult", "answer_query"]
