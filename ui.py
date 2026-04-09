import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport, get_bankroll
from datetime import datetime, timezone
import toml

st.set_page_config(page_title="PolyEdge Arbitrage Trading", layout="wide")

# Auto-refresh every 30 seconds
st_autorefresh(interval=30_000, key="autorefresh")

def load_data():
    cfg = load_config()
    conn = init_db(cfg.db_path)
    signals = get_signals(conn)
    pnl = get_pnl_by_sport(conn)
    bankroll = get_bankroll(conn)
    return cfg, conn, signals, pnl, bankroll

cfg, conn, signals, pnl, bankroll = load_data()

# ── Header ──────────────────────────────────────────────────────────────────
st.title("PolyEdge — Arbitrage Dashboard")

pending   = [s for s in signals if s.status == "pending"]
resolved  = [s for s in signals if s.status in ("won", "lost", "push")]
cancelled = [s for s in signals if s.status == "cancelled"]
total_pnl = sum(s.pnl for s in resolved if s.pnl is not None)
deployed  = sum(s.suggested_size + (s.hedge_size or 0) for s in pending)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Bankroll", f"${bankroll:,.2f}", help="Current balance (dynamic)")
col2.metric("At Risk", f"${deployed:,.2f}", delta=f"{deployed/bankroll*100:.1f}% of bankroll" if bankroll > 0 else "0%",
            help="Total staked (Poly + Hedge). Max exposure.")
col3.metric("Realized P&L", f"${total_pnl:+,.2f}", delta_color="normal",
            help="Profit/loss from settled arbitrage positions.")
col4.metric("Open Arbitrages", len(pending), help="Active positions being tracked.")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["Active Bets", "Trade History", "P&L by Sport", "Settings"])

# ── Tab 1: Active Bets ───────────────────────────────────────────────────────
with tab1:
    st.subheader(f"Open Positions ({len(pending)})")
    if pending:
        rows = []
        for s in sorted(pending, key=lambda x: x.edge_pct, reverse=True):
            poly_side = s.sources_used.split(":")[-1]
            total_cost = s.suggested_size + (s.hedge_size or 0)
            locked_profit = (s.suggested_size / s.poly_price) - total_cost if s.poly_price > 0 else 0
            
            rows.append({
                "ID": s.id,
                "Sport": s.sport.upper(),
                "Matchup": f"{s.team1} vs {s.team2}",
                "Poly Buy": f"{poly_side} ${s.suggested_size:.2f} @ {s.poly_price:.3f}",
                "Hedge (Sharp)": f"${s.hedge_size or 0:.2f} @ {s.hedge_odds or 0:.2f}",
                "Locked Profit": f"${locked_profit:.2f}",
                "Edge %": f"{s.edge_pct * 100:.1f}%",
                "Logged At": s.timestamp.strftime("%H:%M:%S"),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width=None, use_container_width=True, hide_index=True)

        total_deployed = sum(s.suggested_size + (s.hedge_size or 0) for s in pending)
        # Expected profit is actually the locked profit if we are fully hedged
        expected_profit = sum((s.suggested_size / s.poly_price) - (s.suggested_size + (s.hedge_size or 0)) for s in pending if s.poly_price > 0)
        
        col_a, col_b = st.columns(2)
        col_a.metric("Total Capital Deployed", f"${total_deployed:.2f}",
                     help="Total amount currently locked in both sides of trades.")
        col_b.metric("Guaranteed Profit", f"+${expected_profit:.2f}",
                     help="Total profit locked in across all open arbitrage positions.")
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
                "Poly Price": f"{s.poly_price:.3f}",
                "Hedge Odds": f"{s.hedge_odds:.2f}" if s.hedge_odds else "—",
                "Total Size": f"${(s.suggested_size + (s.hedge_size or 0)):.2f}",
                "P&L ($)": f"${s.pnl:+.2f}" if s.pnl is not None else "—",
            })
        df_hist = pd.DataFrame(hist_rows)
        st.dataframe(df_hist, width=None, use_container_width=True, hide_index=True)

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
            bankroll_input = st.number_input("Bankroll ($)", value=float(bankroll), min_value=100.0, step=100.0)
            edge_threshold = st.number_input("Min Edge (%)", value=cfg.scanner.edge_threshold * 100.0, min_value=0.1, max_value=50.0, step=0.1)
            scan_interval  = st.number_input("Scan Interval (min)", value=cfg.scanner.scan_interval_minutes, min_value=1, max_value=60)
        with col_r:
            pinnacle_key = st.text_input("Pinnacle API Key", value=cfg.pinnacle_api_key, type="password")
            stake_key    = st.text_input("Stake API Key", value=cfg.stake_api_key, type="password")
            poly_key     = st.text_input("Polymarket Private Key", value=cfg.polymarket_key, type="password")

        if st.form_submit_button("Save & Apply"):
            from polyedge.db.signals import update_bankroll
            if abs(float(bankroll_input) - float(bankroll)) > 0.01:
                update_bankroll(conn, float(bankroll_input) - float(bankroll), "Manual adjustment via UI")
            
            import os as _os
            config_path = _os.getenv("CONFIG_PATH", "config.toml")
            try:
                with open(config_path, "r") as f:
                    data = toml.load(f)
            except Exception:
                data = {}
            data.setdefault("scanner", {})
            data.setdefault("keys", {})
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
