import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport
from datetime import datetime, timezone
import toml

st.set_page_config(page_title="PolyEdge Paper Trading", layout="wide")

# Auto-refresh every 30 seconds
st_autorefresh(interval=30_000, key="autorefresh")

def load_data():
    cfg = load_config()
    conn = init_db(cfg.db_path)
    signals = get_signals(conn)
    pnl = get_pnl_by_sport(conn)
    return cfg, conn, signals, pnl

cfg, conn, signals, pnl = load_data()

# ── Header ──────────────────────────────────────────────────────────────────
st.title("PolyEdge — Paper Trading Dashboard")

pending   = [s for s in signals if s.status == "pending"]
resolved  = [s for s in signals if s.status in ("won", "lost", "push")]
cancelled = [s for s in signals if s.status == "cancelled"]
total_pnl = sum(s.pnl for s in resolved if s.pnl is not None)
deployed  = sum(s.suggested_size for s in pending)
bankroll  = cfg.scanner.bankroll

col1, col2, col3, col4 = st.columns(4)
col1.metric("Bankroll", f"${bankroll:,.2f}", help="Starting capital (paper)")
col2.metric("At Risk", f"${deployed:,.2f}", delta=f"{deployed/bankroll*100:.1f}% of bankroll",
            help="Sum of open bet stakes. Not all will lose — this is max exposure.")
col3.metric("Realized P&L", f"${total_pnl:+,.2f}", delta_color="normal",
            help="Profit/loss from settled bets only.")
col4.metric("Open Bets", len(pending), help="Active positions being tracked.")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["Active Bets", "Trade History", "P&L by Sport", "Settings"])

# ── Tab 1: Active Bets ───────────────────────────────────────────────────────
with tab1:
    st.subheader(f"Open Positions ({len(pending)})")
    if pending:
        rows = []
        for s in sorted(pending, key=lambda x: x.edge_pct, reverse=True):
            unrealized_pct = None  # would need current price for this
            rows.append({
                "ID": s.id,
                "Sport": s.sport.upper(),
                "Matchup": f"{s.team1} vs {s.team2}",
                "Game Date": s.game_date.strftime("%b %d %H:%M UTC"),
                "Entry Edge": f"{s.edge_pct * 100:.1f}%",
                "Entry Price": f"{s.poly_price:.3f}",
                "Fair Value": f"{s.fair_value:.3f}",
                "Sources": s.sources_used,
                "Size ($)": f"${s.suggested_size:.2f}",
                "Kelly f": f"{s.kelly_fraction:.3f}",
                "Logged At": s.timestamp.strftime("%H:%M:%S"),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        total_deployed = sum(s.suggested_size for s in pending)
        expected_profit = sum(s.suggested_size * s.edge_pct for s in pending)
        max_win = sum(s.suggested_size * (1.0 / s.poly_price - 1.0) for s in pending)
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Capital at Risk", f"${total_deployed:.2f}",
                     help="Total staked. Full loss only if every bet loses.")
        col_b.metric("Expected Profit", f"+${expected_profit:.2f}",
                     help="Sum of (stake × edge%). The long-run average gain if edge holds.")
        col_c.metric("Best Case (all win)", f"+${max_win:.2f}",
                     help="Theoretical profit if every open bet wins.")
    else:
        st.info("No open positions. Scanner is running — new edges will appear here automatically.")

    st.caption(f"Auto-refreshes every 30s · Last load: {datetime.now().strftime('%H:%M:%S')}")

# ── Tab 2: Trade History ─────────────────────────────────────────────────────
with tab2:
    st.subheader("Resolved Trades")
    if resolved or cancelled:
        hist_rows = []
        for s in sorted(resolved + cancelled, key=lambda x: x.timestamp, reverse=True):
            icon = "✅" if s.status == "won" else ("❌" if s.status == "lost" else ("🚫" if s.status == "cancelled" else "➖"))
            hist_rows.append({
                "Result": icon,
                "Sport": s.sport.upper(),
                "Matchup": f"{s.team1} vs {s.team2}",
                "Game Date": s.game_date.strftime("%b %d"),
                "Edge at Entry": f"{s.edge_pct * 100:.1f}%",
                "Entry Price": f"{s.poly_price:.3f}",
                "Exit Price": f"{s.outcome_price:.3f}" if s.outcome_price is not None else "—",
                "Size ($)": f"${s.suggested_size:.2f}",
                "P&L ($)": f"${s.pnl:+.2f}" if s.pnl is not None else "—",
            })
        df_hist = pd.DataFrame(hist_rows)
        st.dataframe(df_hist, use_container_width=True, hide_index=True)

        wins   = sum(1 for s in resolved if s.status == "won")
        losses = sum(1 for s in resolved if s.status == "lost")
        total  = len(resolved)
        win_rate = wins / total * 100 if total else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Trades", total)
        c2.metric("Win Rate", f"{win_rate:.0f}%")
        c3.metric("Wins / Losses", f"{wins} / {losses}")
        c4.metric("Net P&L", f"${total_pnl:+.2f}")
    else:
        st.info("No resolved trades yet. The bot auto-resolves when Polymarket prices settle to 0 or 1.")

# ── Tab 3: P&L by Sport ──────────────────────────────────────────────────────
with tab3:
    st.subheader("Realized P&L by Sport")
    if pnl:
        pnl_df = pd.DataFrame(list(pnl.items()), columns=["Sport", "P&L ($)"]).set_index("Sport")
        st.bar_chart(pnl_df)
        st.metric("Total Realized P&L", f"${sum(pnl.values()):+.2f}")
    else:
        st.info("No resolved trades yet.")

# ── Tab 4: Settings ───────────────────────────────────────────────────────────
with tab4:
    st.subheader("Scanner Settings")
    with st.form("settings_form"):
        col_l, col_r = st.columns(2)
        with col_l:
            bankroll_input = st.number_input("Bankroll ($)", value=cfg.scanner.bankroll, min_value=100.0, step=100.0)
            edge_threshold = st.number_input("Min Edge (%)", value=cfg.scanner.edge_threshold * 100.0, min_value=0.1, max_value=50.0, step=0.1)
            scan_interval  = st.number_input("Scan Interval (min)", value=cfg.scanner.scan_interval_minutes, min_value=1, max_value=60)
        with col_r:
            pinnacle_key = st.text_input("Pinnacle API Key", value=cfg.pinnacle_api_key, type="password")
            stake_key    = st.text_input("Stake API Key", value=cfg.stake_api_key, type="password")
            poly_key     = st.text_input("Polymarket Private Key", value=cfg.polymarket_key, type="password")

        if st.form_submit_button("Save & Apply"):
            import os as _os
            config_path = _os.getenv("CONFIG_PATH", "config.toml")
            try:
                with open(config_path, "r") as f:
                    data = toml.load(f)
            except Exception:
                data = {}
            data.setdefault("scanner", {})
            data.setdefault("keys", {})
            data["scanner"]["bankroll"] = float(bankroll_input)
            data["scanner"]["edge_threshold"] = float(edge_threshold) / 100.0
            data["scanner"]["scan_interval_minutes"] = int(scan_interval)
            data["keys"]["pinnacle_api_key"] = pinnacle_key
            data["keys"]["stake_api_key"] = stake_key
            data["keys"]["polymarket_key"] = poly_key
            with open(config_path, "w") as f:
                toml.dump(data, f)
            st.success("Saved. Restart the scanner for interval changes to take effect.")

    st.divider()
    st.subheader("Source Status")
    sources = {
        "Polymarket": ("✅ Live", "green"),
        "Pinnacle (Arcadia)": ("✅ Live", "green"),
        "Stake": ("❌ Cloudflare blocked", "red"),
        "Mise-o-jeu": ("⚠️ Rate limited (429)", "orange"),
    }
    for src, (status, color) in sources.items():
        st.markdown(f"**{src}** — :{color}[{status}]")
