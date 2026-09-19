"""
List prices for the Gemini models we call, USD per 1M tokens.

Source: https://ai.google.dev/gemini-api/docs/pricing (paid tier, text),
checked 2026-09-19. Thinking tokens are billed as output on every model here.
Gemini's prompt_token_count INCLUDES cached tokens, which bill at the cache
rate instead of the input rate; we split them out before pricing.

Each model carries a dated price list so promotional pricing (3.8 Flash
doubles on 2027-01-01) flips automatically and old rows keep the price that
was actually in force when they were written. Unknown models price to None
— the admin page surfaces those rows as "unpriced" instead of silently
counting them as free.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class Price:
    effective_from: date
    input: float      # USD per 1M uncached prompt tokens
    output: float     # USD per 1M output tokens (completion + thinking)
    cached: float     # USD per 1M cached prompt tokens


# Newest entry first; the first entry whose effective_from <= day applies.
PRICES: dict[str, tuple[Price, ...]] = {
    'gemini-3.8-flash': (
        Price(date(2027, 1, 1), input=1.50, output=7.50, cached=0.15),
        Price(date(2026, 9, 2), input=0.75, output=3.75, cached=0.075),
    ),
    'gemini-3.5-flash-lite': (
        Price(date(2026, 1, 1), input=0.30, output=2.50, cached=0.03),
    ),
    'gemini-3.5-flash': (
        Price(date(2026, 1, 1), input=1.50, output=9.00, cached=0.15),
    ),
    # >200k-token prompts bill at 2x input / 1.5x output; we never send those.
    'gemini-3.1-pro-preview': (
        Price(date(2026, 1, 1), input=2.00, output=12.00, cached=0.20),
    ),
    'gemini-2.5-flash': (
        Price(date(2025, 1, 1), input=0.30, output=2.50, cached=0.03),
    ),
    'gemini-2.5-pro': (
        Price(date(2025, 1, 1), input=1.25, output=10.00, cached=0.125),
    ),
}


def price_for(model: str, day: Optional[date] = None) -> Optional[Price]:
    """The price list in force for `model` on `day` (default: today, UTC).
    Model names may carry a `models/` prefix or a `-latest`/`-001` suffix;
    we match the longest known name that prefixes the given one."""
    day = day or datetime.now(timezone.utc).date()
    name = (model or '').removeprefix('models/')
    for known in sorted(PRICES, key=len, reverse=True):
        if name == known or name.startswith(known + '-'):
            for price in PRICES[known]:
                if price.effective_from <= day:
                    return price
            return None
    return None


def estimate_cost_usd(model: str, prompt_tokens: int = 0, cached_tokens: int = 0,
                      completion_tokens: int = 0, thinking_tokens: int = 0,
                      day: Optional[date] = None) -> Optional[float]:
    """Cost of one call, or None when the model is unpriced."""
    price = price_for(model, day)
    if price is None:
        return None
    cached = max(0, min(cached_tokens or 0, prompt_tokens or 0))
    uncached = max(0, (prompt_tokens or 0) - cached)
    output = max(0, completion_tokens or 0) + max(0, thinking_tokens or 0)
    return (uncached * price.input + cached * price.cached + output * price.output) / 1_000_000
