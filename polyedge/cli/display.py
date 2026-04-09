from __future__ import annotations
from rich.console import Console
from rich.table import Table
from rich import box
from polyedge.models import Signal

console = Console()

def print_signals_table(signals: list[Signal], title="PolyEdge Arbitrage Opportunities") -> None:
    if not signals:
        console.print("[yellow]No signals above threshold.[/yellow]"); return
    t = Table(title=title, box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Sport", width=6)
    t.add_column("Matchup", min_width=25)
    t.add_column("Poly (Buy)", justify="right")
    t.add_column("Hedge (Sharp)", justify="right")
    t.add_column("Total Cost", justify="right", style="dim")
    t.add_column("Locked Profit", justify="right", style="bold green")
    t.add_column("Edge %", justify="right", style="bold green")
    
    for s in sorted(signals, key=lambda x: x.edge_pct, reverse=True):
        # Total cost = Poly stake + Hedge stake
        total_cost = s.suggested_size + (s.hedge_size or 0)
        # Payout if Poly wins = s.suggested_size / s.poly_price
        # Locked profit = Payout - Total Cost
        locked_profit = (s.suggested_size / s.poly_price) - total_cost if s.poly_price > 0 else 0
        
        poly_side = s.sources_used.split(":")[-1]
        t.add_row(
            s.sport.upper(),
            f"{s.team1} vs {s.team2}",
            f"{poly_side} ${s.suggested_size:.2f} @ {s.poly_price:.3f}",
            f"HEDGE ${s.hedge_size or 0:.2f} @ {s.hedge_odds or 0:.2f}",
            f"${total_cost:.2f}",
            f"${locked_profit:.2f}",
            f"{s.edge_pct*100:.1f}%"
        )
    console.print(t)

def print_pnl_table(pnl_by_sport: dict[str, float], total: float, current_balance: float) -> None:
    t = Table(title="P&L by Sport", box=box.SIMPLE)
    t.add_column("Sport", style="bold")
    t.add_column("P&L ($)", justify="right")
    for sport, amt in sorted(pnl_by_sport.items()):
        c = "green" if amt >= 0 else "red"
        t.add_row(sport.upper(), f"[{c}]{amt:+.2f}[/{c}]")
    t.add_row("-" * 8, "-" * 10)
    c = "green" if total >= 0 else "red"
    t.add_row("[bold]TOTAL[/bold]", f"[bold {c}]{total:+.2f}[/bold {c}]")
    t.add_row("[bold cyan]BANKROLL[/bold cyan]", f"[bold cyan]${current_balance:.2f}[/bold cyan]")
    console.print(t)

def print_scan_summary(signals_found, markets_scanned, sources, duration_ms) -> None:
    console.print(f"[dim]Scanned {markets_scanned} markets - "
                  f"{signals_found} signal(s) - Sources: {', '.join(sources)} - {duration_ms}ms[/dim]")