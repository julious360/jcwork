"""Render an ``AuditReport`` as the Markdown document the client actually receives.

Written for a reader who will not run the CLI and does not want the architecture.
Order is deliberate: the money first, the method second, the caveats third. A report
that opens with how the identity spine works loses the room before the number lands.
"""

from __future__ import annotations

from decimal import Decimal

from agent.audit.models import AuditReport, Finding

_NA = "—"


def render_markdown(report: AuditReport) -> str:
    client = report.client_name or "Ad account"
    lines: list[str] = [
        f"# Paid acquisition audit — {client}",
        "",
        f"Window: last **{report.window_days} days** · "
        f"Generated: **{report.generated_on:%d %B %Y}** · "
        f"Currency: **{report.currency}**",
        "",
        "---",
        "",
    ]

    lines += _headline(report)
    lines += _summary_table(report)
    lines += _findings_section(report)
    lines += _method()
    lines += _limits(report)
    return "\n".join(lines).rstrip() + "\n"


# ── Sections ──────────────────────────────────────────────────────────────────


def _headline(report: AuditReport) -> list[str]:
    cur = report.currency
    lines = ["## What this is worth", ""]

    if report.monthly_opportunity > 0:
        lines += [
            f"**{_money(report.monthly_opportunity, cur)} per month** is currently "
            "unrecovered — the sum of spend that is provably not returning and revenue "
            "that funding existing winners would return.",
            "",
        ]
    else:
        lines += [
            "No recoverable monthly opportunity was identified in this window. The "
            "account is inside its thresholds on every ad that carries enough data to "
            "judge.",
            "",
        ]

    wasted, under_scaled = len(report.wasted), len(report.under_scaled)
    lines += [
        f"- **{_money(report.monthly_waste, cur)}/mo** on ads with no defensible return "
        f"({wasted} ad{_s(wasted)})",
        f"- **{_money(report.monthly_scale_upside, cur)}/mo** in net revenue left on the "
        f"table by underfunded winners ({under_scaled} ad{_s(under_scaled)})",
    ]
    if report.unverified:
        lines.append(
            f"- **{_money(report.monthly_unverified, cur)}/mo** flowing through ads whose "
            f"outcome the current tracking cannot resolve at all "
            f"({len(report.unverified)} ad{_s(len(report.unverified))})"
        )
    lines.append("")

    gap = report.attribution_gap_pct
    if gap is not None and gap > 0:
        lines += [
            f"Meta reports **{report.platform_conversions:,}** conversions in this window. "
            f"**{report.attributed_conversions:,}** can be traced to a payment. That is a "
            f"**{gap:.0f}% gap** between the dashboard the account is optimised against and "
            "the revenue it is judged on.",
            "",
        ]
    return lines


def _summary_table(report: AuditReport) -> list[str]:
    cur = report.currency
    return [
        "## The window at a glance",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Ads reviewed | {report.ads_reviewed:,} |",
        f"| Spend | {_money(report.total_spend, cur)} |",
        f"| Attributed revenue | {_money(report.total_revenue, cur)} |",
        f"| Blended ROAS | {_ratio(report.blended_roas)} |",
        f"| Blended CPA | {_money_opt(report.blended_cpa, cur)} |",
        f"| Conversions — Meta reported | {report.platform_conversions:,} |",
        f"| Conversions — traced to payment | {report.attributed_conversions:,} |",
        f"| Attribution gap | {_pct(report.attribution_gap_pct)} |",
        "",
    ]


def _findings_section(report: AuditReport) -> list[str]:
    cur = report.currency
    lines: list[str] = []

    lines += _finding_block(
        "1. Spend to stop",
        report.wasted,
        cur,
        "Each of these has spent past the sample-size floor, sits outside the "
        "attribution lag, and still fails its limit on the *optimistic* end of its "
        "confidence interval. These are not close calls.",
        "Nothing in this window qualifies. No ad has both spent enough to judge and "
        "failed its bound.",
        impact_header="Monthly spend recovered",
    )

    lines += _finding_block(
        "2. Spend to add",
        report.under_scaled,
        cur,
        "These clear the scale benchmark on the *pessimistic* end of their interval "
        "and are out of the learning phase. The figure below is one capped budget "
        "step, net of the added spend — not a compounding projection.",
        "No ad currently clears the scale benchmark with enough conversion history to fund safely.",
        impact_header="Net monthly revenue added",
    )

    if report.unverified:
        lines += _finding_block(
            "3. Spend you cannot currently measure",
            report.unverified,
            cur,
            "Identity resolution on these ads is too weak to confirm or rule out "
            "revenue. They are neither wins nor losses today — they are blind spots, "
            "and they are the first thing worth fixing, because every other number on "
            "this page gets better when they shrink.",
            "",
            impact_header="Monthly spend affected",
        )

    if report.pending:
        lines += [
            "## 4. Ads that look worse than they are",
            "",
            f"{len(report.pending)} ad{_s(len(report.pending))} fall inside the "
            "attribution lag: the spend is booked but the revenue has not finished "
            "landing. On a Meta dashboard they read as failures today. Pausing them "
            "now is the single most common way a well-run account loses a winner.",
            "",
            "| Ad | Spend | Revenue so far |",
            "|---|---:|---:|",
        ]
        lines += [
            f"| `{f.ad_id}` | {_money(f.spend, cur)} | {_money(f.revenue, cur)} |"
            for f in report.pending
        ]
        lines.append("")

    return lines


def _finding_block(
    title: str,
    findings: list[Finding],
    currency: str,
    preamble: str,
    empty_note: str,
    *,
    impact_header: str,
) -> list[str]:
    lines = [f"## {title}", ""]
    if not findings:
        if not empty_note:
            return []
        return [*lines, empty_note, ""]

    lines += [preamble, ""]
    lines += [
        f"| Ad | Spend | Revenue | ROAS | {impact_header} | Why |",
        "|---|---:|---:|---:|---:|---|",
    ]
    lines += [
        f"| `{f.ad_id}` | {_money(f.spend, currency)} | {_money(f.revenue, currency)} | "
        f"{_ratio(f.roas)} | {_money(f.monthly_impact, currency)} | {f.detail} |"
        for f in findings
    ]
    lines.append("")
    return lines


def _method() -> list[str]:
    return [
        "## How these numbers were produced",
        "",
        "Revenue is not taken from Meta. Every figure above comes from a join that "
        "walks each click through to a settled payment:",
        "",
        "```",
        "ad id (stamped into utm_content) → web session → CRM contact → "
        "payment processor → payment",
        "```",
        "",
        "Four properties of that method are worth stating, because they are what make "
        "the conclusions differ from the platform's own reporting:",
        "",
        "1. **Revenue is credited to the click date, not the payment date.** Spend and "
        "revenue on the same row describe the same cohort. Crediting on payment date "
        "smears a Monday click across a Friday row and makes ROAS meaningless.",
        "2. **Revenue is net of refunds.** Gross revenue flatters every ad that sells "
        "to the wrong customer.",
        "3. **The trailing attribution lag is excluded from judgement**, not counted as "
        "failure. Ads inside it appear in their own section above rather than being "
        "scored.",
        "4. **Every hop records how it matched and how confident that match is.** A "
        "deterministic pass-through is not the same quality of evidence as an "
        "email-hash join, and low-confidence ads are reported as unmeasurable rather "
        "than scored on numbers that cannot bear it.",
        "",
        "Pause and scale calls are made on **confidence bounds, not point estimates** — "
        "an ad is only called wasteful when the optimistic end of its interval still "
        "fails, and only called underfunded when the pessimistic end still clears. "
        "Ads below the sample-size floor or inside the platform learning phase are not "
        "judged at all.",
        "",
    ]


def _limits(report: AuditReport) -> list[str]:
    bullets = [
        "- **Whether the thresholds are right for this account.** The limits applied "
        "here are the configured ones. Tuning them against this account's real margin "
        "structure is a separate exercise, and it changes some of the calls above.",
        "- **Whether the creative is good.** This measures money, not ideas. An ad can "
        "clear every bound here and still be the reason the brand looks generic.",
        "- **Incrementality.** Attributed revenue is revenue that followed a click. "
        "Proving the click *caused* the purchase needs a holdout test, which this "
        "window does not contain.",
    ]
    if report.unverified:
        count = len(report.unverified)
        bullets.append(
            f"- **{count} ad{_s(count)} could not be measured at all** at the confidence "
            "floor used here. Until that is fixed, treat the totals above as a lower "
            "bound on what is knowable."
        )
    return ["## What this audit does not tell you", "", *bullets, ""]


# ── Formatting ────────────────────────────────────────────────────────────────


def _money(value: Decimal, currency: str) -> str:
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get(currency, "")
    return f"{symbol}{value:,.0f}" if symbol else f"{value:,.0f} {currency}"


def _money_opt(value: Decimal | None, currency: str) -> str:
    return _NA if value is None else _money(value, currency)


def _ratio(value: Decimal | None) -> str:
    return _NA if value is None else f"{value:.2f}x"


def _pct(value: Decimal | None) -> str:
    return _NA if value is None else f"{value:.0f}%"


def _s(count: int) -> str:
    return "" if count == 1 else "s"
