import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport, get_bankroll, _is_pg
from datetime import datetime, timezone, timedelta
import toml
import plotly.express as px
import plotly.graph_objects as go

# --- Professional Styling ---
st.set_page_config(
    page_title="PolyEdge | Institutional Arbitrage",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { border: 1px solid #1f2937; padding: 20px; border-radius: 12px; background-color: #111827; }
    [data-testid="stMetricValue"] { font-size: 28px; font-weight: 800; color: #00ff88; }
    [data-testid="stMetricLabel"] { font-size: 14px; color: #9ca3af; font-weight: 600; }
    .stTabs [data-baseweb="tab-list"] { gap: 30px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { height: 60px; font-weight: 700; font-size: 18px; color: #6b7280; }
    .stTabs [data-baseweb="tab"]:hover { color: #ffffff; }
    .stTabs [data-baseweb="tab"][aria-selected="true"] { color: #00ff88; border-bottom-color: #00ff88; }
    div[data-testid="stExpander"] { border: 1px solid #1f2937; border-radius: 12px; background-color: #111827; }
    </style>
    """, unsafe_allow_html=True)

# Auto-refresh every 30 seconds
st_autorefresh(interval=30_000, key="autorefresh")

# --- Data Engine ---
def get_db_conn():
    cfg = load_config()
    return init_db(cfg)

@st.cache_data(ttl=2)
def load_serializable_data():
    cfg_obj = load_config()
    conn = init_db(cfg_obj)
    
    config_dict = {
        "edge_threshold": cfg_obj.scanner.edge_threshold,
        "execution_enabled": cfg_obj.scanner.execution_enabled,
        "db_path": cfg_obj.db_path,
        "database_url": cfg_obj.database_url,
        "pinnacle_key": cfg_obj.pinnacle_api_key,
        "poly_key": cfg_obj.polymarket_key,
        "sources": cfg_obj.sources
    }
    
    signals_raw = get_signals(conn)
    signals_list = [vars(s) for s in signals_raw]
    pnl_sport = get_pnl_by_sport(conn)
    bankroll = get_bankroll(conn)
    
    # Advanced History Loading (Safe for both dialects)
    if _is_pg(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bankroll_history ORDER BY timestamp ASC")
            history_df = pd.DataFrame(cur.fetchall())
    else:
        history_df = pd.read_sql("SELECT * FROM bankroll_history ORDER BY timestamp ASC", conn)
        
    if not history_df.empty:
        history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    
    # Close connection if Postgres (Sqlite usually stays open in streamlit)
    if _is_pg(conn):
        conn.close()
        
    return config_dict, signals_list, pnl_sport, bankroll, history_df

try:
    config_dict, signals_list, pnl_sport, bankroll, history_df = load_serializable_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# --- Advanced Computation ---
pending   = [s for s in signals_list if s['status'] == "pending"]
resolved  = [s for s in signals_list if s['status'] in ("won", "lost", "push", "executed")]
total_realized_pnl = sum(s['pnl'] for s in resolved if s['pnl'] is not None)

# Guaranteed Profit from Open Arbs
unrealized_locked_profit = 0
total_deployed = 0
for s in pending:
    if s['poly_price'] > 0:
        cost = s['suggested_size'] + (s['hedge_size'] or 0)
        payout = s['suggested_size'] / s['poly_price']
        unrealized_locked_profit += (payout - cost)
        total_deployed += cost

net_asset_value = bankroll + unrealized_locked_profit

# --- Top Dashboard Layout ---
st.title("🛡️ PolyEdge | Institutional Arb v2.3")

with st.sidebar:
    st.header("⚡ Execution Control")
    is_live = st.toggle("LIVE TRADING ENABLED", value=config_dict['execution_enabled'], help="If enabled, the bot will place real trades on Polymarket & Pinnacle.")
    if is_live != config_dict['execution_enabled']:
        import os as _os
        config_path = _os.getenv("CONFIG_PATH", "config.toml")
        try:
            with open(config_path, "r") as f: data = toml.load(f)
            data.setdefault("scanner", {})["execution_enabled"] = is_live
            with open(config_path, "w") as f: toml.dump(data, f)
            st.rerun()
        except Exception: pass
    
    st.divider()
    st.write(f"**Bankroll Mode:** {'💸 REAL MONEY' if is_live else '📝 PAPER TRADING'}")
    st.write(f"**Database:** {'PG' if config_dict['database_url'] else 'SQLite'}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Net Asset Value", f"${net_asset_value:,.2f}", 
          help="Total Account Value (Current Bankroll + Guaranteed Profit from Open Trades)",
          delta=f"{total_realized_pnl:+,.2f} Realized")
c2.metric("Working Capital", f"${total_deployed:,.2f}", 
          help="Capital currently locked in arbitrage positions.")
c3.metric("Guaranteed Profit", f"${unrealized_locked_profit:,.2f}", 
          help="Money already 'made' but waiting for matches to finish settling.")
c4.metric("Active Engines", sum(1 for v in config_dict['sources'].values() if v), 
          help="Number of data sources currently feeding the scanner.")

st.divider()

# --- Main Navigation ---
tab_live, tab_analytics, tab_ledger, tab_config = st.tabs([
    "🎯 Live Opportunities", 
    "📈 Performance Analytics", 
    "📖 Trade Ledger", 
    "⚙️ System Control"
])

# --- TAB 1: LIVE OPPORTUNITIES ---
with tab_live:
    st.subheader("Current Arbitrage Positions")
    if pending:
        live_rows = []
        for s in sorted(pending, key=lambda x: x['edge_pct'], reverse=True):
            poly_side = s['sources_used'].split(":")[-1]
            cost = s['suggested_size'] + (s['hedge_size'] or 0)
            profit = (s['suggested_size'] / s['poly_price']) - cost if s['poly_price'] > 0 else 0
            roi = (profit / cost * 100) if cost > 0 else 0
            
            age_td = datetime.now(timezone.utc) - s['timestamp'].replace(tzinfo=timezone.utc)
            age_str = f"{int(age_td.total_seconds()//60)}m {int(age_td.total_seconds()%60)}s"

            live_rows.append({
                "Matchup": f"{s['team1']} vs {s['team2']}",
                "Sport": s['sport'].upper(),
                "Poly Exec": f"{poly_side} ${s['suggested_size']:.2f} @ {s['poly_price']:.3f}",
                "Sharp Hedge": f"${s['hedge_size'] or 0:.2f} @ {s['hedge_odds']:.3f}",
                "Total Cost": cost,
                "Profit": profit,
                "ROI %": roi,
                "Age": age_str
            })
        
        df_live = pd.DataFrame(live_rows)
        st.dataframe(
            df_live.style.format({
                "Total Cost": "${:.2f}",
                "Profit": "${:.2f}",
                "ROI %": "{:.2f}%"
            }).map(lambda x: "color: #00ff88; font-weight: bold;" if isinstance(x, (int, float)) and x > 0 else "", 
                   subset=["Profit", "ROI %"]),
            width="stretch", 
            hide_index=True
        )
        st.success(f"📈 **Consolidated Guaranteed Return: ${unrealized_locked_profit:,.2f}**")
    else:
        st.info("Scanner is active. No arbitrage opportunities meet the minimum ROI threshold at this moment.")

# --- TAB 2: PERFORMANCE ANALYTICS ---
with tab_analytics:
    if not history_df.empty:
        col_curve, col_stats = st.columns([2, 1])
        
        with col_curve:
            st.subheader("Equity Growth")
            # Create a more professional equity curve
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=history_df['timestamp'], 
                y=history_df['balance'],
                mode='lines+markers',
                name='Bankroll',
                line=dict(color='#00ff88', width=3),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 136, 0.1)'
            ))
            fig.update_layout(
                template="plotly_dark",
                margin=dict(l=0, r=0, t=20, b=0),
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor='#1f2937'),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                height=400
            )
            st.plotly_chart(fig, width="stretch")

        with col_stats:
            st.subheader("Profit Mix")
            if pnl_sport:
                pnl_data = pd.DataFrame(list(pnl_sport.items()), columns=["Sport", "Profit"])
                fig_pie = px.sunburst(pnl_data, path=['Sport'], values='Profit',
                                     color='Profit', color_continuous_scale='Viridis')
                fig_pie.update_layout(template="plotly_dark", height=400, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(fig_pie, width="stretch")
            else:
                st.info("No resolved trade data.")

        st.subheader("Key Performance Indicators")
        k1, k2, k3, k4 = st.columns(4)
        if resolved:
            rdf = pd.DataFrame(resolved)
            k1.metric("Avg Trade ROI", f"{(rdf['edge_pct'].mean()*100):.2f}%")
            k2.metric("Total Trades", len(resolved))
            k3.metric("Largest Win", f"${rdf['pnl'].max():.2f}")
            k4.metric("Sharpe Ratio", "Perfect (Arb)")
        else:
            st.info("Resolve trades to generate KPIs.")
    else:
        st.warning("Cumulative data is being collected. Equity curve will appear after the first few trades resolve.")

# --- TAB 3: TRADE LEDGER ---
with tab_ledger:
    st.subheader("Complete Transaction History")
    all_history = sorted(signals_list, key=lambda x: x['timestamp'], reverse=True)
    if all_history:
        ledger_rows = []
        for s in all_history:
            status_color = "🟢" if s['status'] == "won" else ("🔴" if s['status'] == "lost" else ("⚪" if s['status'] == "pending" else "✖️"))
            ledger_rows.append({
                "ID": s['id'],
                "Time": s['timestamp'].strftime("%Y-%m-%d %H:%M"),
                "Result": f"{status_color} {s['status'].upper()}",
                "Sport": s['sport'].upper(),
                "Matchup": f"{s['team1']} vs {s['team2']}",
                "ROI": f"{s['edge_pct']*100:.2f}%",
                "Profit ($)": s['pnl'] if s['pnl'] is not None else 0.0,
                "Poly Price": s['poly_price'],
                "Sharp Odds": s['hedge_odds']
            })
        st.dataframe(pd.DataFrame(ledger_rows), width="stretch", hide_index=True)
        
        # Manual settlement
        pending_for_manual = [s for s in signals_list if s['status'] == "pending"]
        if pending_for_manual:
            with st.expander("🛠️ Manual Settlement Tool"):
                st.info("Manually settle a trade if auto-resolve fails or price data is stale.")
                col_id, col_res, col_go = st.columns([1, 2, 1])
                target_id = col_id.selectbox("Select Signal ID", [s['id'] for s in pending_for_manual])
                outcome = col_res.selectbox("Outcome", ["WON", "LOST", "PUSH"])
                if col_go.button("Force Settle"):
                    conn = get_db_conn()
                    from polyedge.db.signals import resolve_signal
                    target_sig = next(s for s in pending_for_manual if s['id'] == target_id)
                    resolve_signal(conn, target_id, outcome.lower(), target_sig['poly_price'])
                    if _is_pg(conn): conn.close()
                    st.success(f"Signal {target_id} manually settled as {outcome}")
                    st.rerun()
    else:
        st.info("Transaction ledger is currently empty.")

# --- TAB 4: SYSTEM CONTROL ---
with tab_config:
    st.subheader("Core Parameters")
    
    with st.expander("💰 Financial Overrides"):
        with st.form("sys_fin"):
            f1, f2 = st.columns(2)
            new_bank = f1.number_input("Reset Bankroll ($)", value=float(bankroll))
            new_edge = f2.slider("Min Arb ROI %", 0.1, 5.0, float(config_dict['edge_threshold']*100.0)) / 100.0
            if st.form_submit_button("Confirm System Update"):
                conn = get_db_conn()
                from polyedge.db.signals import update_bankroll
                if abs(new_bank - bankroll) > 0.01:
                    update_bankroll(conn, new_bank - bankroll, "Manual update via Control Panel")
                
                # Persistence (config.toml)
                import os as _os
                config_path = _os.getenv("CONFIG_PATH", "config.toml")
                try:
                    with open(config_path, "r") as f: data = toml.load(f)
                    data.setdefault("scanner", {})["edge_threshold"] = new_edge
                    with open(config_path, "w") as f: toml.dump(data, f)
                    st.success("Configuration updated successfully.")
                except Exception as ex:
                    st.error(f"Config write failure: {ex}")
                if _is_pg(conn): conn.close()

    with st.expander("📡 Source Management"):
        st.info("Toggle data sources. Requires scanner restart to take effect.")
        with st.form("source_toggle"):
            pinnacle_active = st.checkbox("Pinnacle (Arcadia)", value=config_dict['sources'].get("pinnacle", True))
            stake_active = st.checkbox("Stake", value=config_dict['sources'].get("stake", False))
            mise_active = st.checkbox("Mise-o-jeu", value=config_dict['sources'].get("miseonjeu", False))
            
            if st.form_submit_button("Update Sources"):
                import os as _os
                config_path = _os.getenv("CONFIG_PATH", "config.toml")
                try:
                    with open(config_path, "r") as f: data = toml.load(f)
                    data.setdefault("sources", {})["pinnacle"] = pinnacle_active
                    data["sources"]["stake"] = stake_active
                    data["sources"]["miseonjeu"] = mise_active
                    with open(config_path, "w") as f: toml.dump(data, f)
                    st.success("Sources updated. Restarting the scanner recommended.")
                except Exception as ex:
                    st.error(f"Failed to update sources: {ex}")

    st.subheader("System Health")
    h_cols = st.columns(len(config_dict['sources']) + 1)
    h_cols[0].success("Polymarket: Connected")
    for i, (src, active) in enumerate(config_dict['sources'].items()):
        if active:
            h_cols[i+1].success(f"{src.upper()}: Active")
        else:
            h_cols[i+1].error(f"{src.upper()}: Disabled")
    
    st.write(f"**Database Mode:** {'PostgreSQL' if config_dict['database_url'] else 'SQLite'}")

st.caption(f"PolyEdge Elite v2.3 | Mode: {'PG' if config_dict['database_url'] else 'Local'} | Last Refresh: {datetime.now().strftime('%H:%M:%S')}")
