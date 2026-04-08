from __future__ import annotations
from rich.console import Console
from rich.table import Table
from rich import box
from polyedge.models import Signal

console = Console()

def print_signals_table(signals: list[Signal], title="PolyEdge Opportunities") -> None:
    if not signals:
        console.print("[yellow]No signals above threshold.[/yellow]"); return
    t = Table(title=title, box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Sport", width=6)
    t.add_column("Matchup", min_width=28)
    t.add_column("Game Date", width=16)
    t.add_column("Edge %", justify="right", style="bold green")
    t.add_column("Poly Price", justify="right")
    t.add_column("Fair Value", justify="right")
    t.add_column("Sources", style="dim")
    t.add_column("Size ($)", justify="right", style="bold yellow")
    for s in sorted(signals, key=lambda x: x.edge_pct, reverse=True):
        t.add_row(s.sport.upper(), f"{s.team1} vs {s.team2}",
                  s.game_date.strftime("%b %d %H:%M"),
                  f"{s.edge_pct*100:.1f}%", f"{s.poly_price:.3f}",
                  f"{s.fair_value:.3f}", s.sources_used, f"${s.suggested_size:.2f}")
    console.print(t)

def print_pnl_table(pnl_by_sport: dict[str, float], total: float) -> None:
    t = Table(title="P&L by Sport", box=box.SIMPLE)
    t.add_column("Sport", style="bold")
    t.add_column("P&L ($)", justify="right")
    for sport, amt in sorted(pnl_by_sport.items()):
        c = "green" if amt >= 0 else "red"
        t.add_row(sport.upper(), f"[{c}]{amt:+.2f}[/{c}]")
    t.add_row("-"*8, "-"*10)
    c = "green" if total >= 0 else "red"
    t.add_row("[bold]TOTAL[/bold]", f"[bold {c}]{total:+.2f}[/bold {c}]")
    console.print(t)

def print_scan_summary(signals_found, markets_scanned, sources, duration_ms) -> None:
    console.print(f"[dim]Scanned {markets_scanned} markets - "
                  f"{signals_found} signal(s) - Sources: {', '.join(sources)} - {duration_ms}ms[/dim]")