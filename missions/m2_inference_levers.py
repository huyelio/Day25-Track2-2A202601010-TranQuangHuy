"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num
from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}
CACHE_WRITE_COST = 0.20  # Extra cache write/storage cost as a fraction of one normal input read.
REASONING_TRAFFIC_CAP = 0.05


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = no_cache_opt_cost = 0.0
    total_tokens = 0
    cache_groups = defaultdict(int)
    cache_read_requests = 0
    reasoning = {
        True: {"requests": 0, "tokens": 0, "cost": 0.0, "wh": 0.0},
        False: {"requests": 0, "tokens": 0, "cost": 0.0, "wh": 0.0},
    }
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_reasoning = bool(int(num(r["is_reasoning"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        row_opt = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        opt_cost += row_opt
        no_cache_opt_cost += pricing.request_cost(inp, out, pin, pout, cached_in=0, batch=is_batch)

        if cached > 0:
            cache_read_requests += 1
            cache_groups[(r["team"], r["project"], r["route_tier"])] += 1

        reason_bucket = reasoning[is_reasoning]
        reason_bucket["requests"] += 1
        reason_bucket["tokens"] += inp + out
        reason_bucket["cost"] += row_opt
        reason_bucket["wh"] += sustainability.wh_per_query(inp + out, is_reasoning=is_reasoning)

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    avg_cache_reads = cache_read_requests / len(cache_groups) if cache_groups else 0.0
    cache_break_even = pricing.cache_break_even_reads(CACHE_WRITE_COST)
    cache_worth_it = pricing.cache_is_worth_it(avg_cache_reads, CACHE_WRITE_COST)
    cache_savings = max(0.0, no_cache_opt_cost - opt_cost) if cache_worth_it else 0.0

    req_count = len(rows)
    reasoning_req = reasoning[True]["requests"]
    reasoning_share = reasoning_req / req_count if req_count else 0.0
    cost_share = reasoning[True]["cost"] / opt_cost if opt_cost else 0.0
    total_wh = reasoning[True]["wh"] + reasoning[False]["wh"]
    wh_share = reasoning[True]["wh"] / total_wh if total_wh else 0.0

    avg_reason_cost = reasoning[True]["cost"] / reasoning_req if reasoning_req else 0.0
    non_reason_req = reasoning[False]["requests"]
    avg_non_reason_cost = reasoning[False]["cost"] / non_reason_req if non_reason_req else 0.0
    avg_reason_wh = reasoning[True]["wh"] / reasoning_req if reasoning_req else 0.0
    avg_non_reason_wh = reasoning[False]["wh"] / non_reason_req if non_reason_req else 0.0
    cap_requests = int(req_count * REASONING_TRAFFIC_CAP)
    excess_reasoning = max(0, reasoning_req - cap_requests)
    cap_savings_daily = excess_reasoning * max(0.0, avg_reason_cost - avg_non_reason_cost)
    cap_wh_savings = excess_reasoning * max(0.0, avg_reason_wh - avg_non_reason_wh)

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print("\nYour Turn — cache economics")
        print(f"avg cache reads/prefix: {avg_cache_reads:.1f}  break-even: {cache_break_even:.2f}  worth it? {cache_worth_it}")
        print(f"cache savings counted: ${cache_savings:,.2f}/day")
        print("\nYour Turn — reasoning budget")
        print(f"reasoning traffic: {reasoning_share:.1%} of requests, {cost_share:.1%} of optimized cost, {wh_share:.1%} of energy")
        print(f"cap reasoning at {REASONING_TRAFFIC_CAP:.0%}: save ${cap_savings_daily:,.2f}/day and {cap_wh_savings:,.0f} Wh/day")
        print("routing rule: allow reasoning only for complex eval/research tasks; route routine search/RAG to non-reasoning small tier.")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_economics": {
            "avg_reads": round(avg_cache_reads, 2),
            "break_even_reads": round(cache_break_even, 2),
            "worth_it": cache_worth_it,
            "savings_daily": round(cache_savings, 2),
        },
        "reasoning_budget": {
            "traffic_share_pct": round(reasoning_share * 100, 1),
            "cost_share_pct": round(cost_share * 100, 1),
            "energy_share_pct": round(wh_share * 100, 1),
            "cap_savings_daily": round(cap_savings_daily, 2),
            "cap_wh_savings_daily": round(cap_wh_savings, 1),
            "cap_pct": round(REASONING_TRAFFIC_CAP * 100, 1),
        },
    }


if __name__ == "__main__":
    run()
