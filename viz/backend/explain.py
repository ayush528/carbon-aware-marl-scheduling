"""Computed explanations for a planner decision.

The planner has already decided. This module only answers *why* from the numbers
the replay recorded, so it is deliberately small and pure:

* :func:`candidate_verdict` says what happened to one site inside the block the
  planner used (chosen, too expensive, full, a tie) and cites the numbers.
* :func:`item_explanation` says what happened to one queued request (served now,
  deferred to a cheaper slot, forced to its last legal slot, unplaceable) and
  cites the numbers.

No text here is authored per-run: every sentence is built from the arguments, so
a test can assert that the numbers it quotes are the numbers in the payload. If
the trace and the explanation disagree, the explanation is wrong.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

TOL = 1e-6


def _g(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f} g/kWh"


def _gs(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f} GPU-s"


def _kg(value: float | None) -> str:
    return "—" if value is None else f"{value:,.3f} kg"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def candidate_verdict(
    *,
    site: str,
    price: float,
    chosen_site: str,
    chosen_price: float,
    take_gpu_s: float,
    volume_gpu_s: float,
    free_gpu_s: float,
    capacity_gpu_s: float,
    legal: bool = True,
) -> dict[str, Any]:
    """Classify one site in the chosen block, from the recorded ledger.

    Returns ``{status, code, text}`` where ``status`` is ``chosen`` or
    ``rejected``. The codes are stable; the text is generated from the numbers.
    """
    if not legal:
        return {
            "status": "rejected",
            "code": "illegal",
            "text": (
                f"{site}: outside this request's deadline window, so the planner "
                f"could not use it at this slot."
            ),
        }
    if take_gpu_s > TOL:
        if abs(price - chosen_price) > TOL:
            return {
                "status": "chosen",
                "code": "spill",
                "text": (
                    f"{site}: also used — the cheaper block could not hold all "
                    f"{_gs(volume_gpu_s)}, so {_gs(take_gpu_s)} spilled here at {_g(price)}."
                ),
            }
        return {
            "status": "chosen",
            "code": "chosen",
            "text": (
                f"{site}: {_g(price)}, the cheapest legal block with capacity "
                f"({_gs(free_gpu_s)} free of {_gs(capacity_gpu_s)} in the block); "
                f"{_gs(take_gpu_s)} placed here."
            ),
        }
    if free_gpu_s <= TOL:
        return {
            "status": "rejected",
            "code": "full",
            "text": (
                f"{site}: no capacity left in this block — {_gs(capacity_gpu_s)} "
                f"capacity, {_gs(free_gpu_s)} free after earlier assignments, "
                f"{_gs(volume_gpu_s)} of this request."
            ),
        }
    delta = price - chosen_price
    if delta > TOL:
        relative = 100.0 * delta / chosen_price if chosen_price > TOL else None
        relative_text = f" ({_pct(relative)})" if relative is not None else ""
        return {
            "status": "rejected",
            "code": "pricier",
            "text": (
                f"{site}: {_g(price)}, {delta:+.1f} g/kWh{relative_text} above "
                f"{chosen_site} at {_g(chosen_price)}."
            ),
        }
    if delta < -TOL:
        # The planner prices cheapest-first, so a cheaper block with free capacity
        # would have been used before this one. Record the anomaly rather than
        # dress it up as a decision.
        return {
            "status": "rejected",
            "code": "cheaper_unused",
            "text": (
                f"{site}: {_g(price)} is {-delta:.1f} g/kWh cheaper than "
                f"{chosen_site}, but the request was already fully placed when this "
                f"block was reached — flagged rather than explained away."
            ),
        }
    return {
        "status": "rejected",
        "code": "tie",
        "text": (
            f"{site}: ties {chosen_site} at {_g(price)}; the planner breaks ties by "
            f"slot order, and {chosen_site} came first."
        ),
    }


def _placement_text(
    *,
    chosen_site: str,
    chosen_slot: int,
    chosen_price: float,
    volume_gpu_s: float,
    slot_label: Callable[[int], str],
) -> str:
    return (
        f"Placed {_gs(volume_gpu_s)} at {chosen_site}, {slot_label(chosen_slot)} "
        f"({_g(chosen_price)})."
    )


def item_explanation(
    *,
    item_id: str,
    class_label: str,
    volume_gpu_s: float,
    slot: int,
    arrival: int,
    last_legal_slot: int,
    chosen_slot: int | None,
    chosen_site: str | None,
    chosen_price: float | None,
    now_price: float | None,
    executed_now_gpu_s: float,
    deferred_gpu_s: float,
    unassigned_gpu_s: float,
    spilled: bool,
    alternatives: list[dict[str, Any]],
    slot_options: list[dict[str, Any]],
    slot_label: Callable[[int], str] = lambda value: f"slot {value}",
) -> dict[str, Any]:
    """One sentence plus a code for a queued request, built from the trace."""
    expired = last_legal_slot < slot

    if expired:
        return {
            "code": "expired",
            "headline": f"Deadline missed: {class_label}",
            "detail": (
                f"The window closed at {slot_label(last_legal_slot)}. "
                f"{_gs(volume_gpu_s)} can no longer run and is counted as a miss "
                f"this slot."
            ),
            "flags": {"expired": True, "spilled": spilled, "deadline_forced": False},
        }

    if executed_now_gpu_s <= TOL and deferred_gpu_s <= TOL:
        return {
            "code": "no_capacity",
            "headline": f"No legal block with capacity: {class_label}",
            "detail": (
                f"Every legal block between {slot_label(slot)} and "
                f"{slot_label(last_legal_slot)} is full for this request, so "
                f"{_gs(volume_gpu_s)} could not be placed. It stays queued until its "
                f"window closes."
            ),
            "flags": {"expired": False, "spilled": spilled, "deadline_forced": False},
        }

    if chosen_slot is None or chosen_site is None or chosen_price is None:
        return {
            "code": "unplaceable",
            "headline": f"Not placed: {class_label}",
            "detail": f"The plan left {_gs(volume_gpu_s)} unassigned.",
            "flags": {"expired": False, "spilled": spilled, "deadline_forced": False},
        }

    deadline_forced = chosen_slot >= last_legal_slot
    place = _placement_text(
        chosen_site=chosen_site,
        chosen_slot=chosen_slot,
        chosen_price=chosen_price,
        volume_gpu_s=volume_gpu_s,
        slot_label=slot_label,
    )

    if executed_now_gpu_s > TOL and deferred_gpu_s <= TOL:
        code = "served_now_spilled" if spilled else "served_now"
        text = place
        if spilled:
            others = [
                row.get("label", row["site"]) for row in alternatives if row["take_gpu_s"] > TOL
            ]
            text += (
                f" It did not fit in one block, so the remainder spilled to "
                f"{', '.join(site for site in others if site != chosen_site)}."
            )
        return {
            "code": code,
            "headline": f"Run now at {chosen_site}, {slot_label(chosen_slot)}",
            "detail": text,
            "flags": {
                "expired": False,
                "spilled": spilled,
                "deadline_forced": deadline_forced,
            },
        }

    if executed_now_gpu_s <= TOL and deferred_gpu_s > TOL:
        now_option = next((row for row in slot_options if row["slot"] == slot), None)
        now_free = now_option.get("free_gpu_s") if now_option else None
        if now_free is not None and now_free < volume_gpu_s - TOL:
            code = "deferred_capacity"
            reason = (
                f"the current slot has {_gs(now_free)} free across all sites for "
                f"{_gs(volume_gpu_s)} of work, so the plan placed it at "
                f"{slot_label(chosen_slot)}"
            )
        elif deadline_forced:
            code = "deferred_to_deadline"
            reason = f"no later block is legal — {slot_label(chosen_slot)} is its last legal slot"
        elif now_price is not None and chosen_price < now_price - TOL:
            code = "deferred_cheaper"
            reason = (
                f"{slot_label(chosen_slot)} prices {_g(chosen_price)} against "
                f"{_g(now_price)} now, {now_price - chosen_price:.1f} g/kWh cheaper"
            )
        else:
            code = "deferred_capacity"
            reason = f"the plan held it for {slot_label(chosen_slot)}"
        detail = f"{place} Held because {reason}."
        if deadline_forced and code != "deferred_to_deadline":
            detail += f" {slot_label(chosen_slot)} is its last legal slot."
        return {
            "code": code,
            "headline": f"Deferred to {chosen_site}, {slot_label(chosen_slot)}",
            "detail": detail,
            "flags": {
                "expired": False,
                "spilled": spilled,
                "deadline_forced": deadline_forced,
            },
        }

    # Some now, some later.
    return {
        "code": "split_now_and_later",
        "headline": f"Partly now, partly later: {class_label}",
        "detail": (
            f"{_gs(executed_now_gpu_s)} runs now and {_gs(deferred_gpu_s)} is "
            f"reserved for {slot_label(chosen_slot)} at {chosen_site} "
            f"({_g(chosen_price)})."
            + (
                f" {_gs(unassigned_gpu_s)} has no capacity in its window."
                if unassigned_gpu_s > TOL
                else ""
            )
        ),
        "flags": {"expired": False, "spilled": spilled, "deadline_forced": deadline_forced},
    }


def candidate_sort_key(row: dict[str, Any]) -> tuple[float, int]:
    """The planner's own order: price first, then the earlier slot."""
    return (float(row["price"]), int(row["slot"]))
