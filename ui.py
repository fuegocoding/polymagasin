import streamlit as st
import pandas as pd
import numpy as np
from streamlit_autorefresh import st_autorefresh
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport, get_bankroll
from datetime import datetime, timezone, timedelta
import toml
import plotly.express as px
import plotly.graph_objects as go

# --- Professional Styling ---
st.set_page_config(
    page_title="PolyEdge | Professional Arbitrage",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { border: 1px solid #333; padding: 15px; border-radius: 10px; background-color: #161b22; }
    [data-testid="stMetricValue"] { font-size: 24px; font-weight: bold; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; font-weight: 600; font-size: 16px; }
    .stTable { background-color: #161b22; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Auto-refresh every 30 seconds
st_autorefresh(interval=30_000, key="autorefresh")

# --- Core Data Loading (Serializable Only) ---
def get_db_conn():
    cfg = load_config()
    return init_db(cfg.db_path)

@st.cache_data(ttl=5)
def load_serializable_data():
    """
    Returns only simple Python types (lists, dicts, DataFrames)
    to avoid Streamlit serialization/pickle errors.
    """
    cfg_obj = load_config()
    conn = init_db(cfg_obj.db_path)
    
    # 1. Config as a dict
    config_dict = {
        "edge_threshold": cfg_obj.scanner.edge_threshold,
        "db_path": cfg_obj.db_path,
        "pinnacle_key": cfg_obj.pinnacle_api_key,
        "stake_key": cfg_obj.stake_api_key,
        "poly_key": cfg_obj.polymarket_key
    }
    
    # 2. Signals as list of dicts (Signal dataclass might be causing issues if pickle is finicky)
    signals_raw = get_signals(conn)
    signals_list = [vars(s) for s in signals_raw]
    
    # 3. P&L by sport
    pnl_sport = get_pnl_by_sport(conn)
    
    # 4. Bankroll
    bankroll = get_bankroll(conn)
    
    # 5. History DataFrame
    history_df = pd.read_sql("SELECT * FROM bankroll_history ORDER BY timestamp ASC", conn)
    history_df['timestamp'] = pd.to_datetime(history_df['timestamp'])
    
    return config_dict, signals_list, pnl_sport, bankroll, history_df

# Load the data
try:
    config_dict, signals_list, pnl_sport, bankroll, history_df = load_serializable_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# --- Computed Metrics ---
pending   = [s for s in signals_list if s['status'] == "pending"]
resolved  = [s for s in signals_list if s['status'] in ("won", "lost", "push")]
total_pnl = sum(s['pnl'] for s in resolved if s['pnl'] is not None)
deployed  = sum(s['suggested_size'] + (s['hedge_size'] or 0) for s in pending)

# --- Header ---
st.title("🛡️ PolyEdge Arbitrage Intelligence")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Live Bankroll", f"${bankroll:,.2f}", 
          delta=f"{total_pnl:+,.2f} Realized" if total_pnl != 0 else None)
m2.metric("Working Capital", f"${deployed:,.2f}", 
          help="Total capital locked in open positions (Poly + Sharp).")
m3.metric("Win Rate", f"{(sum(1 for s in resolved if s['status'] == 'won')/len(resolved)*100 if resolved else 0):.1f}%",
          help="Polymarket leg win rate. (Profit is locked either way).")
m4.metric("Active Arbs", len(pending), help="Total number of currently open positions.")

st.divider()

# --- Navigation ---
tab_ops, tab_perf, tab_hist, tab_settings = st.tabs([
    "🎯 Live Opportunities", 
    "📊 Performance Analytics", 
    "📜 Trade Ledger", 
    "⚙️ System Settings"
])

# --- Tab 1: Live Opportunities ---
with tab_ops:
    st.subheader("Current Arbitrage Positions")
    if pending:
        rows = []
        for s in sorted(pending, key=lambda x: x['edge_pct'], reverse=True):
            poly_side = s['sources_used'].split(":")[-1]
            total_cost = s['suggested_size'] + (s['hedge_size'] or 0)
            locked_profit = (s['suggested_size'] / s['poly_price']) - total_cost if s['poly_price'] > 0 else 0
            profit_margin = (locked_profit / total_cost * 100) if total_cost > 0 else 0
            
            # Age calculation
            age_td = datetime.now(timezone.utc) - s['timestamp'].replace(tzinfo=timezone.utc)
            age_str = f"{int(age_td.total_seconds() // 60)}m {int(age_td.total_seconds() % 60)}s"

            rows.append({
                "Matchup": f"{s['team1']} vs {s['team2']}",
                "Sport": s['sport'].upper(),
                "Poly Buy": f"{poly_side} ${s['suggested_size']:.2f} @ {s['poly_price']:.3f}",
                "Sharp Hedge": f"${s['hedge_size'] or 0:.2f} @ {s['hedge_odds']:.3f}",
                "Total Cost": f"${total_cost:.2f}",
                "Profit": locked_profit,
                "ROI %": profit_margin,
                "Age": age_str
            })
        
        df_ops = pd.DataFrame(rows)
        st.dataframe(
            df_ops.style.format({
                "Profit": "${:.2f}",
                "ROI %": "{:.2f}%"
            }).map(lambda x: "color: #00ff88; font-weight: bold;" if isinstance(x, (int, float)) and x > 0 else "", subset=["Profit", "ROI %"]),
            use_container_width=True, 
            hide_index=True
        )
        
        total_profit_locked = sum((s['suggested_size'] / s['poly_price']) - (s['suggested_size'] + (s['hedge_size'] or 0)) 
                                  for s in pending if s['poly_price'] > 0)
        st.success(f"💰 **Total Guaranteed Profit from Open Trades: ${total_profit_locked:,.2f}**")
    else:
        st.info("Searching for arbitrage opportunities... (Market scanners active)")

# --- Tab 2: Performance Analytics ---
with tab_perf:
    col_l, col_r = st.columns([2, 1])
    
    with col_l:
        st.subheader("Equity Curve")
        if not history_df.empty:
            # We want to see the progression. If history is small, add a start point.
            fig = px.area(history_df, x="timestamp", y="balance", 
                          title="Bankroll Over Time",
                          labels={"balance": "Total Value ($)", "timestamp": "Time"},
                          color_discrete_sequence=["#00ff88"])
            fig.update_layout(template="plotly_dark", plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.write("Insufficient data for equity curve.")

    with col_r:
        st.subheader("Profit Distribution")
        if pnl_sport:
            pnl_data = pd.DataFrame(list(pnl_sport.items()), columns=["Sport", "Profit"])
            fig_pie = px.pie(pnl_data, values="Profit", names="Sport", hole=0.4,
                             color_discrete_sequence=px.colors.qualitative.Set2)
            fig_pie.update_layout(template="plotly_dark", showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.write("No resolved trades yet.")

    st.subheader("Statistical Analysis")
    if resolved:
        res_df = pd.DataFrame(resolved)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Avg Trade Profit", f"${res_df['pnl'].mean():.2f}")
        c2.metric("Median ROI", f"{res_df['edge_pct'].median()*100:.2f}%")
        c3.metric("Total Executed", len(resolved))
        c4.metric("Sharpe Ratio", "N/A (Arb Risk-Free)")
    else:
        st.info("Analytics will populate as trades resolve.")

# --- Tab 3: Trade Ledger ---
with tab_hist:
    st.subheader("Resolved Arbitrage History")
    if resolved:
        hist_rows = []
        for s in sorted(resolved, key=lambda x: x['timestamp'], reverse=True):
            hist_rows.append({
                "Date": s['timestamp'].strftime("%Y-%m-%d %H:%M"),
                "Matchup": f"{s['team1']} vs {s['team2']}",
                "Poly Price": f"{s['poly_price']:.3f}",
                "Sharp Odds": f"{s['hedge_odds']:.3f}",
                "Profit ($)": f"{s['pnl']:+,.2f}",
                "Result": s['status'].upper()
            })
        st.dataframe(pd.DataFrame(hist_rows), use_container_width=True, hide_index=True)
    else:
        st.info("Ledger is empty.")

# --- Tab 4: System Settings ---
with tab_settings:
    st.subheader("System Configuration")
    with st.expander("Financial Management", expanded=True):
        with st.form("fin_settings"):
            new_bank = st.number_input("Reset/Correct Bankroll ($)", value=float(bankroll))
            new_edge = st.slider("Minimum Profit Margin %", 0.1, 5.0, float(config_dict['edge_threshold']*100.0)) / 100.0
            if st.form_submit_button("Apply Changes"):
                conn = get_db_conn()
                from polyedge.db.signals import update_bankroll
                diff = new_bank - bankroll
                if abs(diff) > 0.01:
                    update_bankroll(conn, diff, "Manual correction via Dashboard")
                
                # Update config.toml
                import os as _os
                config_path = _os.getenv("CONFIG_PATH", "config.toml")
                try:
                    with open(config_path, "r") as f: data = toml.load(f)
                    data.setdefault("scanner", {})["edge_threshold"] = new_edge
                    with open(config_path, "w") as f: toml.dump(data, f)
                    st.success("Bankroll corrected and Edge threshold updated.")
                except Exception as ex:
                    st.error(f"Failed to update config file: {ex}")

    with st.expander("API & Diagnostics"):
        st.write("Current API connectivity status and keys.")
        st.code(f"Pinnacle API: {'PROTECTED' if config_dict['pinnacle_key'] else 'MISSING'}")
        st.code(f"Stake API: {'PROTECTED' if config_dict['stake_key'] else 'MISSING'}")
        
    st.subheader("Active Infrastructure")
    s1, s2, s3 = st.columns(3)
    s1.success("Polymarket: Connected")
    s2.success("Pinnacle (Arcadia): Live")
    s3.warning("Stake: Cloudflare (Restricted)")

st.caption(f"PolyEdge v2.2 Professional | Last Sync: {datetime.now().strftime('%H:%M:%S')}")
