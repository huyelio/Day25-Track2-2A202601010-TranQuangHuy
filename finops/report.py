"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(baseline_usd: float, optimized_usd: float, levers: dict,
                 sustainability: dict | None = None, period: str = "monthly",
                 extensions: dict | None = None, analysis: dict | None = None) -> str:
    """Return a markdown cost-optimization report."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}  ",
        f"**Baseline spend:** ${baseline_usd:,.0f}  ",
        f"**Optimized spend:** ${optimized_usd:,.0f}  ",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")
    if analysis:
        lie_ids = ", ".join(analysis.get("util_lie_gpus", [])) or "none"
        top_lever = analysis.get("top_lever", "Purchasing")
        lines += [
            "",
            "## Technical Analysis",
            "",
            "### GPU-Util Lie",
            "",
            f"- Flagged GPUs: {lie_ids}",
            "- GPU-Util only says the device clock was busy; it does not prove the workload used tensor FLOPs efficiently.",
            "- Low MFU with high GPU-Util usually points to memory stalls, tiny kernels, launch overhead, or a workload shape that keeps the GPU occupied without doing enough useful math.",
            "- Cost impact: these GPUs are billed for full GPU-hours while delivering only a fraction of peak model throughput, so right-sizing and workload tuning are higher-value than buying more GPUs.",
            "",
            "### Action Priority",
            "",
            f"1. Apply {top_lever} first because it is the largest measured monthly savings lever.",
            "2. Keep cascade, prompt caching, and batch API enabled because they reduce unit cost in $/1M-token, not just $/GPU-hour.",
            "3. Right-size util-lie GPUs and shut down idle capacity before adding new GPU quota.",
            "4. Move from showback to chargeback now that tag coverage is above the 80% governance gate.",
        ]
    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Cheapest+cleanest region: {sustainability.get('best_region', 'n/a')}",
            "- Carbon-aware placement matters because the same workload can have very different emissions and electricity cost across regions.",
        ]
    if extensions:
        lines += ["", "## Your Turn Extensions", ""]
        cache = extensions.get("cache_economics")
        if cache:
            lines += [
                "### Cache Economics",
                "",
                f"- Avg cache reads per prefix: {cache.get('avg_reads', 0):.1f}",
                f"- Break-even reads: {cache.get('break_even_reads', 0):.2f}",
                f"- Cache worth it: {cache.get('worth_it', False)}",
                f"- Measured cache savings: ${cache.get('savings_daily', 0) * 30:,.0f}/month",
                "",
            ]
        reasoning = extensions.get("reasoning_budget")
        if reasoning:
            lines += [
                "### Reasoning Budget",
                "",
                f"- Reasoning traffic: {reasoning.get('traffic_share_pct', 0):.1f}% of requests",
                f"- Share of optimized cost: {reasoning.get('cost_share_pct', 0):.1f}%",
                f"- Share of serving energy: {reasoning.get('energy_share_pct', 0):.1f}%",
                f"- Cap at {reasoning.get('cap_pct', 0):.0f}% traffic: save ${reasoning.get('cap_savings_daily', 0) * 30:,.0f}/month and {reasoning.get('cap_wh_savings_daily', 0) * 30:,.0f} Wh/month",
                "- Routing rule: reserve reasoning for complex eval/research work; route routine search and RAG to the non-reasoning small tier.",
            ]
    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a simple savings bar chart PNG. Returns the path. No-op if matplotlib absent."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, vals, color="#2e548a")
    ax.set_ylabel("Savings (USD / month)")
    ax.set_title("GPU cost savings by FinOps lever")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
