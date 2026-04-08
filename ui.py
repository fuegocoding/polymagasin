import streamlit as st
import pandas as pd
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport
from datetime import datetime, timezone

st.set_page_config(page_title="PolyEdge Arbitrage Dashboard", layout="wide")


def load_data():
    cfg = load_config()
    conn = init_db(cfg.db_path)
    signals = get_signals(conn)
    pnl = get_pnl_by_sport(conn)
    return cfg, signals, pnl


cfg, signals, pnl = load_data()

st.title("📈 PolyEdge Arbitrage Bot Dashboard")

tab1, tab2, tab3 = st.tabs(["Active Signals", "P&L Summary", "Settings & API Keys"])

with tab1:
    st.header("Pending Opportunities")
    pending = [s for s in signals if s.status == "pending"]
    if pending:
        df = pd.DataFrame(
            [
                {
                    "Time": s.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "Sport": s.sport.upper(),
                    "Matchup": f"{s.team1} vs {s.team2}",
                    "Edge": f"{s.edge_pct * 100:.1f}%",
                    "Poly Price": f"{s.poly_price:.3f}",
                    "Fair Value": f"{s.fair_value:.3f}",
                    "Sources": s.sources_used,
                    "Kelly Size": f"${s.suggested_size:.2f}",
                    "Link": s.poly_market_id,
                }
                for s in pending
            ]
        )
        st.dataframe(df, use_container_width=True)
    else:
        st.info(
            "No pending opportunities at the moment. Ensure your API keys are valid and the background watch process is running."
        )

with tab2:
    st.header("P&L by Sport")
    if pnl:
        st.bar_chart(
            pd.DataFrame(list(pnl.items()), columns=["Sport", "PnL"]).set_index("Sport")
        )
        total = sum(pnl.values())
        st.metric("Total PnL", f"${total:.2f}")
    else:
        st.info("No resolved signals yet. Run `python main.py resolve` after an event.")

with tab3:
    st.header("Settings & API Configuration")
    st.write(
        "Configure your scanner settings and API keys here. Changes are saved to `config.toml`."
    )

    with st.form("settings_form"):
        st.subheader("Scanner Settings")
        scan_interval = st.number_input(
            "Scan Interval (minutes)",
            value=cfg.scanner.scan_interval_minutes,
            min_value=1,
            max_value=1440,
        )
        edge_threshold = st.number_input(
            "Minimum Edge Threshold (%)",
            value=cfg.scanner.edge_threshold * 100.0,
            min_value=0.1,
            max_value=100.0,
            step=0.1,
        )
        bankroll = st.number_input(
            "Total Bankroll ($)",
            value=cfg.scanner.bankroll,
            min_value=10.0,
            max_value=1000000.0,
            step=10.0,
        )

        st.subheader("API Keys")
        pinnacle_key = st.text_input(
            "Pinnacle Basic Auth (base64 username:password)",
            value=cfg.pinnacle_api_key,
            type="password",
        )
        stake_key = st.text_input(
            "Stake API Key (x-access-token)", value=cfg.stake_api_key, type="password"
        )
        miseonjeu_key = st.text_input(
            "Mise-o-jeu API Key / Header", value=cfg.miseonjeu_api_key, type="password"
        )
        poly_key = st.text_input(
            "Polymarket Private Key", value=cfg.polymarket_key, type="password"
        )

        if st.form_submit_button("Save Configuration"):
            import toml

            try:
                with open("config.toml", "r") as f:
                    data = toml.load(f)
            except Exception:
                data = {}
            if "keys" not in data:
                data["keys"] = {}
            if "scanner" not in data:
                data["scanner"] = {}

            # Save scanner settings
            data["scanner"]["scan_interval_minutes"] = int(scan_interval)
            data["scanner"]["edge_threshold"] = float(edge_threshold) / 100.0
            data["scanner"]["bankroll"] = float(bankroll)

            # Save keys
            data["keys"]["pinnacle_api_key"] = pinnacle_key
            data["keys"]["stake_api_key"] = stake_key
            data["keys"]["miseonjeu_api_key"] = miseonjeu_key
            data["keys"]["polymarket_key"] = poly_key

            with open("config.toml", "w") as f:
                toml.dump(data, f)
            st.success(
                "Settings saved to config.toml! Restart the background scanner for interval changes to apply."
            )
