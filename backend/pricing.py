# USD per million tokens, (input, output). Source: platform.claude.com/docs/en/pricing
_PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

_DEFAULT_PRICING = _PRICING_PER_MTOK["claude-sonnet-4-6"]


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = _PRICING_PER_MTOK.get(model, _DEFAULT_PRICING)
    return (input_tokens / 1_000_000) * input_price + (output_tokens / 1_000_000) * output_price
