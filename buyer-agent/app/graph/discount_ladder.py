"""The BUYER agent's own copy of a staged discount-ask ladder — mirrors
the shape of the seller's backend/app/agent/discount_ladder.py (Phase
10, Part A) but is an INDEPENDENT reimplementation, not an import. Same
independence rule this whole client already follows (see client.py's
docstring): this agent has no code-level connection to the seller's
backend, only to its public HTTP interface.

Used so the buyer's own negotiation asks escalate in fixed, predictable
steps (5% then 10%) rather than the LLM inventing a number each round —
matching Part A's "the number is deterministic, only the conversation
context is LLM-shaped" principle on the buyer's side too. Each round's
ask is a proposal SENT to /agent/v1/negotiate; the seller's own gate is
still the only authority on whether it's actually approved.
"""

from dataclasses import dataclass

DEFAULT_LADDER: list[float] = [5.0, 10.0]


@dataclass(frozen=True)
class LadderRung:
    attempt_number: int
    discount_pct: float
    is_final_rung: bool


def rung_for_attempt(attempt_number: int) -> LadderRung:
    index = min(attempt_number - 1, len(DEFAULT_LADDER) - 1)
    return LadderRung(
        attempt_number=attempt_number,
        discount_pct=DEFAULT_LADDER[index],
        is_final_rung=attempt_number > len(DEFAULT_LADDER),
    )


def ladder_total_value(original_unit_price: int, quantity: int, discount_pct: float) -> int:
    unit_price = round(original_unit_price * (1 - discount_pct / 100))
    return unit_price * quantity
