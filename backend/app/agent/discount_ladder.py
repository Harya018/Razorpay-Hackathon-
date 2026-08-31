"""The SELLER AGENT's own discount-escalation STRATEGY — a staged
percentage ladder (5% then 10%, matching a real salesperson's pacing)
that decide_to_offer/propose_offer read deterministically.

This is explicitly NOT enforcement. policy-gate/app/rules/
merchant_rules.py's max_discount_pct remains the only actual authority
on what's allowed — every ladder rung still goes through /evaluate
exactly like any other proposed offer, and the gate can still reject a
rung if it happens to exceed a product's real ceiling (nothing here
reads or depends on merchant_rules.py). This file only ever answers
"what should we propose next," never "what's allowed." Deliberately
kept on the backend side, in the seller agent's own package — not
inside policy-gate — for that reason.
"""

from dataclasses import dataclass

# Percent off, in escalation order. attempt 1 -> ladder[0], attempt 2 ->
# ladder[1], etc. Once attempt_number reaches the ladder's length, the
# LAST rung repeats (see rung_for_attempt) rather than inventing a new
# number — that's the "state plainly this is our best" step.
DEFAULT_LADDER: list[float] = [5.0, 10.0]

# Per-product overrides — same pattern as merchant_rules.py's
# PRODUCT_RULES. Any product_id not listed here falls back to
# DEFAULT_LADDER. Add a line here for any SKU that should escalate
# differently (e.g. a thinner-margin product with smaller steps).
PRODUCT_LADDERS: dict[int, list[float]] = {}


@dataclass(frozen=True)
class LadderRung:
    attempt_number: int
    discount_pct: float
    is_final_rung: bool  # True once attempt_number has reached the ladder's last rung


def get_ladder(product_id: int) -> list[float]:
    return PRODUCT_LADDERS.get(product_id, DEFAULT_LADDER)


def rung_for_attempt(product_id: int, attempt_number: int) -> LadderRung:
    """attempt_number is 1-indexed, matching nodes.py's existing
    `attempt_number = state["turn_count"] + 1` convention. Clamps to the
    ladder's last rung once attempt_number reaches or exceeds its
    length — no new percentage past that point, just different framing
    around the same ceiling value (is_final_rung=True).
    """
    ladder = get_ladder(product_id)
    index = min(attempt_number - 1, len(ladder) - 1)
    return LadderRung(
        attempt_number=attempt_number,
        discount_pct=ladder[index],
        # Strictly GREATER than the ladder's length: attempt_number ==
        # len(ladder) is still the last NEW rung (e.g. attempt 2 -> 10%,
        # a fresh escalation from attempt 1's 5%) — only attempt_number ==
        # len(ladder) + 1 (e.g. attempt 3, with a 2-rung ladder) repeats
        # that same value AND switches to "this is our best" framing.
        is_final_rung=attempt_number > len(ladder),
    )


def ladder_total_value(original_unit_price: int, cart_quantity: int, discount_pct: float) -> int:
    """Total cart price (paise) at this rung's discount. Rounds at the
    UNIT level first, then multiplies by quantity — the SAME order of
    operations as merchant_rules.min_allowed_unit_price — so a rung
    meant to land exactly at the merchant's ceiling doesn't miss it by a
    paise from a different rounding order.
    """
    unit_price = round(original_unit_price * (1 - discount_pct / 100))
    return unit_price * cart_quantity
