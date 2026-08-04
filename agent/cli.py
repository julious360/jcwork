"""Command line interface."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import typer

from agent.config import get_settings, load_brand_guide, load_campaign, load_thresholds
from agent.logging_setup import configure_logging

app = typer.Typer(help="Autonomous Facebook Ads marketing agent", no_args_is_help=True)
db_app = typer.Typer(help="Database migrations and inspection")
app.add_typer(db_app, name="db")


@app.callback()
def _init() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.environment != "development")


# ── Setup ─────────────────────────────────────────────────────────────────────


@db_app.command("migrate")
def db_migrate() -> None:
    """Apply ClickHouse and Postgres migrations."""
    from agent.ops.db import Database
    from agent.warehouse.client import WarehouseClient

    pg = Database().migrate()
    typer.echo(f"Postgres:   {', '.join(pg) or 'none'}")
    ch = WarehouseClient().migrate()
    typer.echo(f"ClickHouse: {', '.join(ch) or 'none'}")


@app.command()
def doctor() -> None:
    """Report which integrations are live versus mocked, and check connectivity."""
    from agent.creative.providers import provider_health
    from agent.ops.db import Database
    from agent.research.providers import build_provider
    from agent.warehouse.client import WarehouseClient

    settings = get_settings()
    typer.echo(f"environment:  {settings.environment}")
    typer.echo(f"meta dry_run: {settings.meta.dry_run}  (tier: {settings.meta.access_tier})")

    for name, status in provider_health(settings).items():
        typer.echo(f"{name + ':':13} {status}")
    typer.echo(f"research:     {build_provider(settings).name}")

    for label, probe in (
        ("postgres", lambda: Database().cursor().__enter__().execute("SELECT 1")),
        ("clickhouse", lambda: WarehouseClient().query("SELECT 1")),
    ):
        try:
            probe()
            typer.echo(f"{label + ':':13} reachable")
        except Exception as exc:
            typer.echo(f"{label + ':':13} UNREACHABLE ({type(exc).__name__})")


@app.command()
def config() -> None:
    """Show the active campaign, thresholds, and brand guide."""
    campaign, thresholds, guide = load_campaign(), load_thresholds(), load_brand_guide()
    typer.echo(f"category:     {campaign.product_category}")
    typer.echo(f"product:      {campaign.product_name}")
    typer.echo(
        f"thresholds:   target CPA {thresholds.target_cpa}, max {thresholds.cpa_max}, "
        f"ROAS min {thresholds.roas_min}, scale {thresholds.roas_scale}"
    )
    typer.echo(
        f"guardrails:   {thresholds.min_spend_multiple}x spend floor, "
        f"{thresholds.confidence_level:.0%} confidence, "
        f"{thresholds.attribution.lag_hours}h attribution lag"
    )
    typer.echo(
        f"blast radius: {thresholds.max_actions_per_run}/run, "
        f"{thresholds.max_actions_per_day}/day, kill_switch={thresholds.kill_switch}"
    )
    typer.echo(f"brand:        {len(guide.palette)} colours, ΔE tolerance {guide.max_delta_e}")


# ── Verification ──────────────────────────────────────────────────────────────


@app.command()
def seed() -> None:
    """Load synthetic warehouse data covering the four canonical loop scenarios.

    Nothing here touches Meta, Stripe, or real money. Follow with ``adagent verify``.
    """
    from agent.seed import load
    from agent.warehouse.client import WarehouseClient

    counts = load(WarehouseClient())
    for table, count in counts.items():
        typer.echo(f"{table + ':':32} {count:>6} rows")
    typer.echo("\nnow run: adagent verify")


@app.command()
def verify() -> None:
    """Run the loop against seeded data and check it reached the right decisions.

    This is the end-to-end proof: migrations applied, the identity spine resolved,
    attribution SQL credited revenue to the right ad, and the guardrails protected
    the two ads that must not be touched.
    """
    from agent.orchestrator.jobs import JobContext, refresh_warehouse
    from agent.seed import EXPECTED

    ctx = JobContext.build(get_settings())
    refresh_warehouse(ctx, {"days": 30, "dry_run": True})
    ctx.queue.claim()  # drop the chained job; we run the loop inline

    from agent.decision.engine import DecisionEngine, default_lookback

    economics = ctx.queries.load_ad_economics(default_lookback(ctx.thresholds))
    result = DecisionEngine(ctx.ledger, ctx.thresholds, None).run(economics, dry_run=True)
    actual = {d.ad_id: str(d.action) for d in result.decisions if d.ad_id}

    typer.echo(f"\nevaluated {result.evaluated} ads\n")
    failures = 0
    for ad_id, expected in EXPECTED.items():
        got = actual.get(ad_id, "MISSING")
        ok = got == expected
        failures += 0 if ok else 1
        typer.echo(f"  {'PASS' if ok else 'FAIL'}  {ad_id:14} expected {expected:14} got {got}")

    typer.echo("")
    for decision in result.actionable:
        typer.echo(f"  {decision.ad_id}: {decision.reason}")

    if failures:
        typer.echo(f"\n{failures} scenario(s) wrong — the warehouse path is broken")
        raise typer.Exit(1)
    typer.echo("\nall scenarios correct: warehouse, attribution, and guardrails all work")


# ── The loop ──────────────────────────────────────────────────────────────────


@app.command()
def loop(
    dry_run: Annotated[
        bool, typer.Option(help="Decide and record, but do not write to Meta")
    ] = True,
    refresh: Annotated[bool, typer.Option(help="Refresh the warehouse mart first")] = True,
) -> None:
    """Run one full decision cycle."""
    from agent.orchestrator.jobs import JobContext, decision_loop, refresh_warehouse

    ctx = JobContext.build(get_settings())
    if refresh:
        typer.echo(json.dumps(refresh_warehouse(ctx, {"days": 30, "dry_run": dry_run}), indent=2))
        # refresh_warehouse queues the loop; run it inline so the CLI is synchronous.
        ctx.queue.claim()
    typer.echo(json.dumps(decision_loop(ctx, {"dry_run": dry_run}), indent=2))


@app.command()
def research(
    category: Annotated[str, typer.Option(help="Override the configured category")] = "",
    limit: Annotated[int, typer.Option(help="Max documents to analyse")] = 50,
    output: Annotated[Path | None, typer.Option(help="Write ranked JSON here")] = None,
) -> None:
    """Rank the top customer pain points."""
    from agent.llm import build_llm
    from agent.research.providers import build_provider
    from agent.research.ranker import PainPointRanker, report_to_json

    settings = get_settings()
    campaign = load_campaign()
    if category:
        campaign = campaign.model_copy(update={"product_category": category})

    provider = build_provider(settings)
    documents = provider.fetch(campaign, limit=limit)
    report = PainPointRanker(build_llm(settings)).rank(documents, campaign, provider.name)

    rendered = report_to_json(report, campaign.top_pain_points)
    if output:
        output.write_text(rendered)
        typer.echo(f"wrote {output}")
    else:
        typer.echo(rendered)


@app.command()
def creative(
    variants: Annotated[int, typer.Option(help="Variants per pain point")] = 2,
) -> None:
    """Research, then generate and validate creative from the top pain points."""
    from agent.orchestrator.jobs import JobContext, generate_creative
    from agent.orchestrator.jobs import research as research_job

    ctx = JobContext.build(get_settings())
    typer.echo(json.dumps(research_job(ctx, {"limit": 50}), indent=2))

    job = ctx.queue.claim()
    if job is None:
        typer.echo("no pain points produced; nothing to generate")
        raise typer.Exit(1)
    payload = {**job.payload, "variants_per_point": variants}
    typer.echo(json.dumps(generate_creative(ctx, payload), indent=2))


@app.command()
def harvest() -> None:
    """Pull fresh external DNA into the pool."""
    from agent.orchestrator.jobs import JobContext, harvest_entropy

    ctx = JobContext.build(get_settings())
    typer.echo(json.dumps(harvest_entropy(ctx, {"limit": 20}), indent=2))


# ── Inspection ────────────────────────────────────────────────────────────────


@app.command()
def actions(
    days: Annotated[int, typer.Option(help="How far back to look")] = 7,
    pending: Annotated[bool, typer.Option(help="Only show actions awaiting approval")] = False,
) -> None:
    """Show the action ledger — what the agent decided, and why."""
    from agent.ops.db import Database
    from agent.ops.ledger import ActionLedger

    ledger = ActionLedger(Database())
    if pending:
        rows = ledger.pending_approval()
        if not rows:
            typer.echo("nothing awaiting approval")
            return
        for row in rows:
            typer.echo(f"[{row.id}] {row.action_type} {row.ad_id or row.adset_id}: {row.reason}")
        return

    with Database().cursor() as cur:
        cur.execute(
            "SELECT created_at, action_type, status, ad_id, adset_id, reason, dry_run "
            "FROM agent_actions WHERE created_at > now() - make_interval(days => %s) "
            "ORDER BY created_at DESC LIMIT 100",
            (days,),
        )
        for row in cur.fetchall():
            flag = " [dry-run]" if row["dry_run"] else ""
            typer.echo(
                f"{row['created_at']:%Y-%m-%d %H:%M} {row['action_type']:14} "
                f"{row['status']:10} {row['ad_id'] or row['adset_id'] or '-':20}{flag}\n"
                f"    {row['reason']}"
            )


@app.command()
def approve(action_id: Annotated[int, typer.Argument(help="Ledger action id")]) -> None:
    """Approve an action that exceeded the human-approval spend threshold."""
    from agent.domain import ActionStatus
    from agent.ops.db import Database
    from agent.ops.ledger import ActionLedger

    ActionLedger(Database()).mark(action_id, ActionStatus.APPROVED)
    typer.echo(f"action {action_id} approved (the next loop will execute it)")


@app.command()
def economics(days: Annotated[int, typer.Option()] = 14) -> None:
    """Show the warehouse view the decision engine reads."""
    from agent.warehouse.client import WarehouseClient
    from agent.warehouse.queries import WarehouseQueries

    since = date.today() - timedelta(days=days)
    rows = WarehouseQueries(WarehouseClient()).load_ad_economics(since)
    if not rows:
        typer.echo("no ad economics found — has the mart been refreshed?")
        return

    header = (
        f"{'ad_id':16} {'spend':>10} {'conv':>6} {'revenue':>12} {'CPA':>8} {'ROAS':>7}  matured"
    )
    typer.echo(header)
    typer.echo("-" * len(header))
    for row in sorted(rows, key=lambda r: r.lifetime_spend, reverse=True):
        cpa = f"{row.cpa:.2f}" if row.cpa is not None else "-"
        roas = f"{row.roas:.2f}" if row.roas is not None else "-"
        typer.echo(
            f"{row.ad_id[:16]:16} {row.spend:>10.2f} {row.attributed_conversions:>6} "
            f"{row.attributed_revenue:>12.2f} {cpa:>8} {roas:>7}  {row.window_matured}"
        )


# ── Long-running processes ────────────────────────────────────────────────────


@app.command()
def worker() -> None:
    """Run the queue worker (Railway service)."""
    from agent.orchestrator.worker import Worker

    Worker().run_forever()


@app.command()
def scheduler() -> None:
    """Run the scheduler (Railway service)."""
    from agent.orchestrator.scheduler import Scheduler

    Scheduler().run_forever()


if __name__ == "__main__":
    app()
