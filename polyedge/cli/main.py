from __future__ import annotations
import asyncio, time
from typing import Optional
import httpx, typer
from rich.console import Console
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import (
    get_signals,
    get_pnl_by_sport,
    resolve_signal,
    get_signal_by_id,
    log_scan,
)
from polyedge.fetchers.polymarket import PolymarketFetcher
from polyedge.fetchers.pinnacle import PinnacleFetcher
from polyedge.fetchers.stake import StakeFetcher
from polyedge.fetchers.miseonjeu import MiseonjeuFetcher
from polyedge.scanner import run_scan
from polyedge.cli.display import (
    print_signals_table,
    print_pnl_table,
    print_scan_summary,
)

app = typer.Typer(help="PolyEdge — Polymarket arbitrage scanner")
console = Console()


def _load(cfg_path="config.toml"):
    cfg = load_config(cfg_path)
    return cfg, init_db(cfg.db_path)


@app.command()
def scan(config: str = typer.Option("config.toml")):
    """Run one scan and show opportunities."""
    asyncio.run(_do_scan(config))


from polyedge.ws import WebSocketManager


@app.command()
def watch(config: str = typer.Option("config.toml")):
    """Continuously scan using WebSocket architecture. Ctrl+C to stop."""
    cfg, conn = _load(config)
    console.print(
        f"[cyan]Connecting to WebSockets for real-time edge scanning (>= {cfg.scanner.edge_threshold * 100}%). Ctrl+C to stop.[/cyan]"
    )

    async def on_update(markets, odds):
        # Triggered whenever new WS data arrives
        sigs = await run_scan(markets, odds, cfg, conn)
        if sigs:
            print_signals_table(sigs)
            log_scan(conn, len(markets), len(sigs), ["websocket"], 0)

    manager = WebSocketManager(cfg, conn, on_update)

    try:
        asyncio.run(manager.start())
    except KeyboardInterrupt:
        manager.stop()
        console.print("\n[yellow]Stopped WebSocket Manager.[/yellow]")


@app.command()
def signals(
    sport: Optional[str] = typer.Option(None),
    min_edge: float = typer.Option(0.0),
    status: Optional[str] = typer.Option(None),
    config: str = typer.Option("config.toml"),
):
    """List signals from DB."""
    cfg, conn = _load(config)
    rows = get_signals(conn, sport=sport, min_edge=min_edge, status=status)
    if not rows:
        console.print("[yellow]No signals.[/yellow]")
        return
    print_signals_table(rows, f"Signals (n={len(rows)})")


@app.command()
def pnl(config: str = typer.Option("config.toml")):
    """P&L summary by sport."""
    _, conn = _load(config)
    by_sport = get_pnl_by_sport(conn)
    if not by_sport:
        console.print("[yellow]No resolved signals yet.[/yellow]")
        return
    print_pnl_table(by_sport, sum(by_sport.values()))


@app.command()
def resolve(
    signal_id: int = typer.Argument(),
    outcome: str = typer.Argument(),
    outcome_price: float = typer.Option(0.0),
    config: str = typer.Option("config.toml"),
):
    """Mark signal as won/lost/push."""
    if outcome not in ("won", "lost", "push"):
        console.print("[red]outcome must be: won / lost / push[/red]")
        raise typer.Exit(1)
    _, conn = _load(config)
    resolve_signal(conn, signal_id, outcome, outcome_price)
    s = get_signal_by_id(conn, signal_id)
    c = "green" if s.pnl >= 0 else "red"
    console.print(f"Signal {signal_id} -> {outcome} | P&L: [{c}]{s.pnl:+.2f}[/{c}]")


async def _do_scan(cfg_path: str) -> None:
    cfg, conn = _load(cfg_path)
    t0 = time.monotonic()
    active = [k for k, v in cfg.sources.items() if v]
    fetchers = {
        "pinnacle": PinnacleFetcher,
        "stake": StakeFetcher,
        "miseonjeu": MiseonjeuFetcher,
    }
    async with httpx.AsyncClient(
        headers={"User-Agent": "PolyEdge/1.0"}, follow_redirects=True
    ) as client:
        poly_task = asyncio.create_task(PolymarketFetcher(client).fetch(cfg.sports))
        sb_tasks = {}
        if "pinnacle" in active:
            sb_tasks["pinnacle"] = asyncio.create_task(
                fetchers["pinnacle"](client, cfg.pinnacle_api_key).fetch(cfg.sports)
            )
        if "stake" in active:
            sb_tasks["stake"] = asyncio.create_task(
                fetchers["stake"](client, cfg.stake_api_key).fetch(cfg.sports)
            )
        if "miseonjeu" in active:
            sb_tasks["miseonjeu"] = asyncio.create_task(
                fetchers["miseonjeu"](client, cfg.miseonjeu_api_key).fetch(cfg.sports)
            )
        poly_markets = await poly_task
        odds_lines = []
        for n, task in sb_tasks.items():
            try:
                odds_lines.extend(await task)
            except Exception as e:
                console.print(f"[red][{n}] {e}[/red]")
    sigs = await run_scan(poly_markets, odds_lines, cfg, conn)
    ms = int((time.monotonic() - t0) * 1000)
    print_signals_table(sigs)
    print_scan_summary(len(sigs), len(poly_markets), active, ms)
    log_scan(conn, len(poly_markets), len(sigs), active, ms)
