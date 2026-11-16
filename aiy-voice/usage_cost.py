"""Calculate USD from provider usage; this is an estimate, not a billing receipt.

Rates per million tokens from https://developers.openai.com/api/docs/pricing
retrieved 2026-11-15. Only GPT-Realtime-2.1 with audio/text (no images) is supported.
Usage input is an authenticated /v1/usage JSON export; no credentials are needed.
"""

import json
import sys
from decimal import Decimal


def cost(usage, model="gpt-realtime-2.1"):
    """Apply cached/uncached modality rates without double-counting cached tokens."""
    if model == "gpt-6-luna":
        details = usage.get("input_tokens_details", {})
        cached = details.get("cached_tokens", 0)
        writes = details.get("cache_write_tokens", 0)
        write_details = details.get("cache_write_tokens_details", {})
        short = write_details.get("ttl_30m_tokens", 0)
        long = write_details.get("ttl_12h_tokens", 0)
        if short + long != writes:
            raise ValueError("Cache-write TTL breakdown unavailable")
        if usage["input_tokens"] > 272000:
            raise ValueError("Long-context search pricing is not supported")
        amount = (
            Decimal(usage["input_tokens"] - cached - writes) * Decimal("0.10")
            + Decimal(cached) * Decimal("0.01")
            + Decimal(short) * Decimal("0.125")
            + Decimal(long) * Decimal("0.25")
            + Decimal(usage["output_tokens"]) * Decimal("0.50")
        ) / 1000000
        return amount + Decimal(usage.get("web_search_calls", 0)) * Decimal("0.01")
    if model != "gpt-realtime-2.1":
        raise ValueError("Unsupported model pricing")
    source = usage["input_token_details"]
    output = usage["output_token_details"]
    cached = source.get("cached_tokens_details", {})
    if source.get("image_tokens", 0):
        raise ValueError("Image pricing is outside this voice-only calculator")
    if sum(cached.values()) != source.get("cached_tokens", 0):
        raise ValueError("Cached token modality breakdown is unavailable")
    amount = Decimal(0)
    for modality, input_rate, output_rate in [("text", 4, 24), ("audio", 32, 64)]:
        key = modality + "_tokens"
        amount += Decimal(source.get(key, 0) - cached.get(key, 0)) * input_rate
        amount += Decimal(cached.get(key, 0)) * Decimal("0.40")
        amount += Decimal(output.get(key, 0)) * output_rate
    # Reasoning text is included in output text tokens; never add it again.
    return amount / 1000000


if __name__ == "__main__":
    records = json.load(sys.stdin)["responses"]
    total = Decimal(0)
    for record in records:
        record_cost = cost(record["usage"], record.get("model", "gpt-realtime-2.1"))
        total += record_cost
        print(record["response_id"], "$" + str(record_cost))
    print("TOTAL_USD", total)
