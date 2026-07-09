import streamlit as st
import pandas as pd
import anthropic
import os
import json
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="Olyns Operational Briefing",
    page_icon="♻️",
    layout="wide"
)

# ── Brand styles ───────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #F5F5F5; }
    .olyns-header {
        background: linear-gradient(135deg, #174B69, #0088FF);
        padding: 2rem; border-radius: 12px;
        margin-bottom: 2rem; color: white;
    }
    .olyns-header h1 { color: white; margin: 0; font-size: 2rem; }
    .olyns-header p { color: rgba(255,255,255,0.85); margin: 0.5rem 0 0 0; }
    .metric-card {
        background: white; border-radius: 10px; padding: 1.2rem;
        text-align: center; border-top: 4px solid #0088FF;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }
    .metric-card .value { font-size: 2rem; font-weight: 700; color: #174B69; }
    .metric-card .label { font-size: 0.8rem; color: #666; margin-top: 0.3rem;
        text-transform: uppercase; letter-spacing: 0.05em; }
    .metric-card.green { border-top-color: #7EC530; }
    .metric-card.orange { border-top-color: #F7944C; }
    .metric-card.red { border-top-color: #EF6243; }
    .flag-card {
        background: white; border-radius: 10px; padding: 1rem 1.2rem;
        border-left: 5px solid #0088FF;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 0.5rem;
    }
    .flag-card.red { border-left-color: #EF6243; background: #FFF3F0; }
    .flag-card.orange { border-left-color: #F7944C; background: #FFF8F0; }
    .flag-card.green { border-left-color: #7EC530; background: #F6FBF0; }
    .flag-card .flag-title { font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.08em; font-weight: 700; color: #666; }
    .flag-card .flag-value { font-size: 1.4rem; font-weight: 700; color: #174B69; margin: 0.2rem 0; }
    .flag-card .flag-sub { font-size: 0.85rem; color: #555; }
    .section-header { color: #174B69; font-weight: 700; font-size: 1.1rem; margin-bottom: 0.5rem; }
    .anomaly-box {
        background: #FFF3F0; border-left: 4px solid #EF6243;
        padding: 0.8rem 1rem; border-radius: 0 8px 8px 0;
        margin-bottom: 0.5rem; font-size: 0.9rem; color: #333333;
    }
    .action-card {
        background: #174B69; color: white; border-radius: 10px;
        padding: 1rem 1.2rem; margin-bottom: 0.8rem;
    }
    .action-card .action-num { font-size: 0.75rem; text-transform: uppercase;
        letter-spacing: 0.1em; color: #7EC530; font-weight: 700; }
    .action-card .action-text { margin-top: 0.3rem; font-size: 0.95rem; }
    .commentary {
        background: white; border-radius: 8px; padding: 1rem;
        border-left: 3px solid #0088FF; font-size: 0.9rem;
        color: #333; margin-top: 0.8rem;
    }
    .comparison-card {
        background: white; border-radius: 10px; padding: 1.2rem;
        border-top: 4px solid #174B69;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06); margin-bottom: 1rem;
    }
    .upload-note {
        background: white; border-radius: 8px; padding: 1rem;
        border: 1px solid #e0e0e0; font-size: 0.85rem;
        color: #555; margin-top: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────
st.markdown("""
<div class="olyns-header">
    <h1>♻️ Olyns Operational Briefing</h1>
    <p>Upload your data exports and generate your briefing</p>
</div>
""", unsafe_allow_html=True)

# ── Constants ──────────────────────────────────────────────────
EXCLUDED_COMPANIES  = {"cocacola", "coca-cola", "coca cola", "e&l", "crv",
                       "donations only", "smr", "obrc"}
OPERATING_START     = 10
OPERATING_END       = 20

# ── Helpers ────────────────────────────────────────────────────
def read_csv(f):
    try:
        return pd.read_csv(f, encoding="utf-8", quotechar='"',
                           on_bad_lines='skip', engine='python')
    except UnicodeDecodeError:
        f.seek(0)
        return pd.read_csv(f, encoding="latin-1", quotechar='"',
                           on_bad_lines='skip', engine='python')

def normalize_cols(df):
    df.columns = (df.columns.str.strip()
                             .str.lower()
                             .str.replace(" ", "_")
                             .str.replace("→_", "")
                             .str.replace("→", ""))
    return df

def operating_hours_overlap(start, end, op_start=OPERATING_START, op_end=OPERATING_END):
    if pd.isna(start) or pd.isna(end) or end <= start:
        return 0.0
    total = 0.0
    current = start
    while current < end:
        day_end   = current.normalize() + pd.Timedelta(days=1)
        window_end = min(end, day_end)
        op_open   = current.normalize() + pd.Timedelta(hours=op_start)
        op_close  = current.normalize() + pd.Timedelta(hours=op_end)
        overlap_start = max(current, op_open)
        overlap_end   = min(window_end, op_close)
        if overlap_end > overlap_start:
            total += (overlap_end - overlap_start).total_seconds() / 3600
        current = day_end
    return round(total, 2)

def format_age(days):
    if pd.isna(days):
        return "—"
    months = int(days // 30)
    years  = months // 12
    rem    = months % 12
    if years > 0:
        return f"{years}y {rem}m" if rem > 0 else f"{years}y"
    return f"{months}m"

import re
def normalize_filename(fname):
    """Strip Metabase export timestamp from filenames.
    e.g. auth_user_2026-06-01T11_00_23.443799355-07_00.csv -> auth_user.csv
    """
    return re.sub(r'_\d{4}-\d{2}-\d{2}T[\d_.\-]+\.csv$', '.csv', fname)

# ── Demo data ────────────────────────────────────────────────────
def get_demo_metrics():
    """Realistic-but-fake metrics dict for demo mode."""
    stores = [
        "Lucky - Downtown", "Safeway - Northgate", "Target - Eastside",
        "FoodMaxx - Central", "Safeway - Westpark", "Lucky - Riverside",
        "Target - Hillside", "Safeway - Midtown", "FoodMaxx - South",
        "Lucky - Lakeside", "Safeway - Creekside", "Target - Sunnyvale",
    ]
    summary = {
        "active_cubes":    12,
        "total_deposits":  4832,
        "total_services":  38,
        "total_maint":     14,
        "avg_full_raw":    6.2,
        "avg_accept_lag":  1.8,
        "flagged_sherpas": 2,
    }
    flags = {
        "cube_full_longest":  {"value": "18.4h",    "location": "Lucky - Downtown",      "sub": "3 services this period"},
        "cube_maint_longest": {"value": "22.1h",    "location": "Safeway - Northgate",   "sub": "2 maint events"},
        "top_deposit_cube":   {"value": "842",      "location": "Target - Eastside",     "sub": "17% of total deposits"},
        "busiest_cube":       {"value": "94 users", "location": "Target - Eastside",     "sub": "62% return rate"},
        "max_csd_location":   {"value": "47 bags",  "location": "Safeway - Westpark",    "sub": "PET: 28 · ALU: 19"},
        "csd_maint_flag":     {"value": "3 sites",  "location": "Lucky Downtown, Safeway Northgate, Target Eastside", "sub": "High CSD + maint overlap"},
    }
    fleet_table = pd.DataFrame(
        [{"Location": s, "Production Date": "2023-01-15", "Active Since": "2023-03-01",
          "Retired Date": "", "Status": "Active", "Age": "2y 9m"} for s in stores] +
        [{"Location": "FoodMaxx - Old Town", "Production Date": "2022-06-10",
          "Active Since": "2022-08-01", "Retired Date": "2024-11-30", "Status": "Retired", "Age": "2y 3m"},
         {"Location": "Lucky - Harbor",      "Production Date": "2022-09-05",
          "Active Since": "2022-11-01", "Retired Date": "2025-02-15", "Status": "Retired", "Age": "2y 3m"}])
    fleet_summary = {"total_ever": 14, "total_active": 12, "total_retired": 2, "avg_age_days": 810}
    deployments_by_month = pd.DataFrame([
        {"deploy_month": "2022-08", "cubes_deployed": 2},
        {"deploy_month": "2022-11", "cubes_deployed": 1},
        {"deploy_month": "2023-03", "cubes_deployed": 8},
        {"deploy_month": "2023-09", "cubes_deployed": 3},
    ])
    deployments_by_year  = pd.DataFrame([
        {"deploy_year": 2022, "cubes_deployed": 3},
        {"deploy_year": 2023, "cubes_deployed": 11},
    ])
    retirements_by_year  = pd.DataFrame([
        {"retire_year": 2024, "cubes_retired": 1},
        {"retire_year": 2025, "cubes_retired": 1},
    ])
    retired_cubes = pd.DataFrame([
        {"Location": "FoodMaxx - Old Town", "Active Since": "2022-08-01", "Retired Date": "2024-11-30"},
        {"Location": "Lucky - Harbor",       "Active Since": "2022-11-01", "Retired Date": "2025-02-15"},
    ])
    col_fi = "Avg Hrs Full incl overnight (service created → completion)"
    col_fo = "Avg Hrs Full op hrs only (service created → completion)"
    q1_full = pd.DataFrame([
        {"store_name": stores[0], col_fi: 18.4, col_fo: 7.2, "Services": 3},
        {"store_name": stores[1], col_fi: 14.1, col_fo: 5.8, "Services": 4},
        {"store_name": stores[2], col_fi: 11.3, col_fo: 4.5, "Services": 5},
        {"store_name": stores[3], col_fi:  8.7, col_fo: 3.9, "Services": 3},
        {"store_name": stores[4], col_fi:  6.2, col_fo: 2.9, "Services": 4},
    ])
    q2_freq = pd.DataFrame([
        {"store_name": stores[0], "maint_transitions": 4},
        {"store_name": stores[1], "maint_transitions": 3},
        {"store_name": stores[5], "maint_transitions": 3},
        {"store_name": stores[2], "maint_transitions": 2},
        {"store_name": stores[7], "maint_transitions": 2},
    ])
    q2_failures = pd.DataFrame([
        {"store_name": stores[0], "highest_priority_problem": "Sensor Fault",    "count": 3},
        {"store_name": stores[1], "highest_priority_problem": "Door Jam",        "count": 2},
        {"store_name": stores[5], "highest_priority_problem": "Sensor Fault",    "count": 2},
        {"store_name": stores[2], "highest_priority_problem": "Network Timeout", "count": 1},
    ])
    col_mi = "Avg Hrs in Maint incl overnight (maint event → next ready)"
    col_mo = "Avg Hrs in Maint op hrs only (maint event → next ready)"
    q3_maint = pd.DataFrame([
        {"store_name": stores[1], col_mi: 22.1, col_mo: 8.4, "Maint Events": 3},
        {"store_name": stores[0], col_mi: 18.3, col_mo: 6.9, "Maint Events": 4},
        {"store_name": stores[5], col_mi: 12.6, col_mo: 4.8, "Maint Events": 3},
    ])
    col_ac = "Avg Hrs to Accept (service created → sherpa accepted)"
    q4_cube = pd.DataFrame([
        {"store_name": s, col_ac: round(1.2 + i * 0.3, 1)} for i, s in enumerate(stores[:8])
    ])
    q5_worst_cancel = pd.DataFrame([
        {"operator_id": 1003, "total_jobs": 12, "cancel_count": 3, "cancel_rate_pct": 25.0},
        {"operator_id": 1007, "total_jobs":  8, "cancel_count": 2, "cancel_rate_pct": 25.0},
        {"operator_id": 1011, "total_jobs": 15, "cancel_count": 2, "cancel_rate_pct": 13.3},
    ])
    q5_top_volume = pd.DataFrame([
        {"operator_id": 1001, "total_jobs": 9, "avg_duration_hrs": 1.4},
        {"operator_id": 1002, "total_jobs": 8, "avg_duration_hrs": 1.6},
        {"operator_id": 1004, "total_jobs": 7, "avg_duration_hrs": 1.3},
        {"operator_id": 1005, "total_jobs": 6, "avg_duration_hrs": 1.8},
        {"operator_id": 1006, "total_jobs": 5, "avg_duration_hrs": 2.1},
    ])
    q5_top_speed = pd.DataFrame([
        {"operator_id": 1004, "avg_duration_hrs": 1.1, "total_jobs": 7},
        {"operator_id": 1001, "avg_duration_hrs": 1.4, "total_jobs": 9},
        {"operator_id": 1002, "avg_duration_hrs": 1.6, "total_jobs": 8},
        {"operator_id": 1008, "avg_duration_hrs": 1.7, "total_jobs": 4},
        {"operator_id": 1005, "avg_duration_hrs": 1.8, "total_jobs": 6},
    ])
    q5_timers   = pd.DataFrame([
        {"operator_id": 1007, "timer_extensions": 4},
        {"operator_id": 1003, "timer_extensions": 3},
        {"operator_id": 1011, "timer_extensions": 2},
    ])
    q5_svc_type = pd.DataFrame([
        {"service_type": "Cube Empty", "count": 31},
        {"service_type": "CSD Pickup", "count":  7},
    ])
    os_breakdown = pd.DataFrame([
        {"os": "Ios",     "user_count": 1842},
        {"os": "Android", "user_count":  963},
    ])
    q6_cohorts = pd.DataFrame([
        {"cohort_month": "2025-10", "total_deposits": 612, "unique_users": 204},
        {"cohort_month": "2025-11", "total_deposits": 743, "unique_users": 231},
        {"cohort_month": "2025-12", "total_deposits": 689, "unique_users": 218},
        {"cohort_month": "2026-01", "total_deposits": 798, "unique_users": 247},
        {"cohort_month": "2026-02", "total_deposits": 841, "unique_users": 263},
        {"cohort_month": "2026-03", "total_deposits": 912, "unique_users": 279},
    ])
    q6_sessions = pd.DataFrame([
        {"store_name": s, "avg_deposits_per_session": round(3.2 + i * 0.4, 1)} for i, s in enumerate(stores[:8])
    ])
    q7_engagement = pd.DataFrame([
        {"store_name": stores[2], "unique_users": 94, "return_users": 58, "return_rate_pct": 61.7},
        {"store_name": stores[0], "unique_users": 81, "return_users": 49, "return_rate_pct": 60.5},
        {"store_name": stores[6], "unique_users": 74, "return_users": 43, "return_rate_pct": 58.1},
        {"store_name": stores[3], "unique_users": 68, "return_users": 38, "return_rate_pct": 55.9},
        {"store_name": stores[4], "unique_users": 62, "return_users": 33, "return_rate_pct": 53.2},
    ])
    q8_retention = pd.DataFrame([
        {"store_name": s, "repeat_users": max(58 - i * 5, 10)} for i, s in enumerate(stores[:8])
    ])
    q9_volume = pd.DataFrame([
        {"store_name": stores[2], "total_deposits": 842},
        {"store_name": stores[0], "total_deposits": 714},
        {"store_name": stores[6], "total_deposits": 631},
        {"store_name": stores[3], "total_deposits": 598},
        {"store_name": stores[4], "total_deposits": 521},
    ])
    q9_brands = pd.DataFrame([
        {"brand": "Coca-Cola", "count": 1284},
        {"brand": "PepsiCo",   "count":  973},
        {"brand": "Nestle",    "count":  641},
        {"brand": "Unilever",  "count":  512},
        {"brand": "Other",     "count": 1422},
    ])
    q9_container = pd.DataFrame([
        {"material": "ALU", "count": 2341},
        {"material": "PET", "count": 1876},
        {"material": "GLS", "count":  412},
        {"material": "BWN", "count":  203},
    ])
    q10_csd_location = pd.DataFrame([
        {"store_name": stores[4], "bag_count": 47},
        {"store_name": stores[1], "bag_count": 31},
        {"store_name": stores[7], "bag_count": 24},
        {"store_name": stores[3], "bag_count": 18},
    ])
    q10_csd_material = pd.DataFrame([
        {"material": "PET", "small": 38, "large / BWN total": 84, "total_containers": 122},
        {"material": "ALU", "small": 21, "large / BWN total": 56, "total_containers":  77},
        {"material": "GLS", "small": 14, "large / BWN total": 29, "total_containers":  43},
        {"material": "BWN", "small":  0, "large / BWN total": 18, "total_containers":  18},
    ])
    q10_csd_depositors = pd.DataFrame([
        {"depositor_id": f"user_{1000+i}", "PET": max(12-i, 0), "ALU": max(8-i, 0), "total": max(20-2*i, 0)}
        for i in range(10)
    ])
    csd_maint_corr = pd.DataFrame([
        {"store_name": stores[0], "csd_bags": 31, "maint_count": 4},
        {"store_name": stores[1], "csd_bags": 47, "maint_count": 3},
        {"store_name": stores[2], "csd_bags": 24, "maint_count": 2},
        {"store_name": stores[7], "csd_bags": 18, "maint_count": 2},
    ])
    return {
        "summary":             summary,
        "flags":               flags,
        "fleet_table":         fleet_table,
        "fleet_summary":       fleet_summary,
        "deployments_by_month":deployments_by_month,
        "deployments_by_year": deployments_by_year,
        "retirements_by_year": retirements_by_year,
        "retired_cubes":       retired_cubes,
        "q1_full":             q1_full,
        "q2_freq":             q2_freq,
        "q2_failures":         q2_failures,
        "q3_maint":            q3_maint,
        "q4_cube":             q4_cube,
        "q5_worst_cancel":     q5_worst_cancel,
        "q5_top_volume":       q5_top_volume,
        "q5_top_speed":        q5_top_speed,
        "q5_timers":           q5_timers,
        "q5_svc_type":         q5_svc_type,
        "q5_flagged":          pd.DataFrame(columns=["operator_id", "sherpa_rating"]),
        "os_breakdown":        os_breakdown,
        "new_users_summary":   {"total": 87, "ios": 54, "android": 33},
        "user_join_os":        pd.DataFrame(columns=["id", "date_joined", "os"]),
        "q6_cohorts":          q6_cohorts,
        "q6_sessions":         q6_sessions,
        "q7_engagement":       q7_engagement,
        "q8_retention":        q8_retention,
        "q9_volume":           q9_volume,
        "q9_brands":           q9_brands,
        "q9_container":        q9_container,
        "q10_csd_location":    q10_csd_location,
        "q10_csd_material":    q10_csd_material,
        "q10_csd_depositors":  q10_csd_depositors,
        "csd_maint_corr":      csd_maint_corr,
        "data_start":          pd.Timestamp("2026-06-01", tz="UTC"),
        "data_end":            pd.Timestamp("2026-06-15", tz="UTC"),
    }

DEMO_SNAPSHOTS = [
    {"snapshot_date": "2026-04-07 to 2026-04-13", "summary": {"active_cubes": 11, "total_deposits": 3921, "total_services": 32, "total_maint": 18, "avg_full_raw": 7.8, "avg_accept_lag": 2.4, "flagged_sherpas": 3}},
    {"snapshot_date": "2026-04-14 to 2026-04-20", "summary": {"active_cubes": 11, "total_deposits": 4104, "total_services": 35, "total_maint": 16, "avg_full_raw": 7.1, "avg_accept_lag": 2.1, "flagged_sherpas": 3}},
    {"snapshot_date": "2026-04-21 to 2026-04-27", "summary": {"active_cubes": 12, "total_deposits": 4389, "total_services": 36, "total_maint": 15, "avg_full_raw": 6.9, "avg_accept_lag": 2.0, "flagged_sherpas": 2}},
    {"snapshot_date": "2026-04-28 to 2026-05-04", "summary": {"active_cubes": 12, "total_deposits": 4512, "total_services": 37, "total_maint": 14, "avg_full_raw": 6.5, "avg_accept_lag": 1.9, "flagged_sherpas": 2}},
    {"snapshot_date": "2026-05-05 to 2026-05-11", "summary": {"active_cubes": 12, "total_deposits": 4698, "total_services": 37, "total_maint": 15, "avg_full_raw": 6.3, "avg_accept_lag": 1.8, "flagged_sherpas": 2}},
    {"snapshot_date": "2026-05-12 to 2026-05-18", "summary": {"active_cubes": 12, "total_deposits": 4832, "total_services": 38, "total_maint": 14, "avg_full_raw": 6.2, "avg_accept_lag": 1.8, "flagged_sherpas": 2}},
]

# ── Tabs ────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["📊 Generate Briefing", "📈 Trend Analysis"])

# ── Data processing ────────────────────────────────────────────
def process_data(uploads):
    auth_user     = normalize_cols(read_csv(uploads["auth_user"]))
    profile       = normalize_cols(read_csv(uploads["api_profile"]))
    collector_all = normalize_cols(read_csv(uploads["api_collector"]))
    #st.write("collector columns:", collector_all.columns.tolist())
    store         = normalize_cols(read_csv(uploads["api_store"]))
    company       = normalize_cols(read_csv(uploads["api_company"]))
    events        = normalize_cols(read_csv(uploads["api_systemevent"]))
    deposit       = normalize_cols(read_csv(uploads["api_deposit"]))
    service       = normalize_cols(read_csv(uploads["api_service"]))
    csddropoff    = normalize_cols(read_csv(uploads["api_csddropoff"]))
    csddropoffbag = normalize_cols(read_csv(uploads["api_csddropoffbag"]))

    if "accept_ation_date" in service.columns:
        service = service.rename(columns={"accept_ation_date": "acceptation_date"})

    # Parse datetimes
    for col in ["created_at"]:
        if col in events.columns:
            events[col] = pd.to_datetime(events[col], utc=True, errors="coerce")
    for col in ["created_at", "updated_at", "acceptation_date", "completion_date"]:
        if col in service.columns:
            service[col] = pd.to_datetime(service[col], utc=True, errors="coerce")
    for col in ["created_at"]:
        if col in csddropoff.columns:
            csddropoff[col] = pd.to_datetime(csddropoff[col], utc=True, errors="coerce")
    if "date" in deposit.columns:
        deposit["date"] = pd.to_datetime(deposit["date"], utc=True, errors="coerce")
    if "date_joined" in auth_user.columns:
        auth_user["date_joined"] = pd.to_datetime(auth_user["date_joined"], utc=True, errors="coerce")
    for col in ["in_service_date", "production_date"]:
        if col in collector_all.columns:
            collector_all[col] = pd.to_datetime(collector_all[col], utc=True, errors="coerce")

    # ── Company + store display names ──────────────────────────
    name_col = next((c for c in company.columns if c.lower().strip() == "name"), None)
    if name_col:
        company["name_lower"] = company[name_col].str.lower().str.strip()
    else:
        company["name_lower"] = ""
    excluded_ids   = company[company["name_lower"].isin(EXCLUDED_COMPANIES)]["id"].tolist()
    store_excluded = store[store["company_id"].isin(excluded_ids)]["id"].tolist()

    store = store.merge(
        company[["id", name_col]].rename(columns={"id": "company_id", name_col: "company_name"}),
        on="company_id", how="left")
    store["display_name"] = (store["company_name"].fillna("") + " " +
                              store["name"].fillna("")).str.strip()

    # ── Fleet overview (all cubes incl retired) ────────────────
    collector_all = collector_all.merge(
        store[["id", "display_name"]].rename(columns={"id": "store_id"}),
        on="store_id", how="left")
    collector_all = collector_all.rename(columns={"display_name": "store_name"})

    # Retirement dates from StatusRetired events
    retired_events = events[events["event"] == "StatusRetired"][["collector_id", "created_at"]].copy()
    retired_events = retired_events.sort_values("created_at").groupby("collector_id").first().reset_index()
    retired_events = retired_events.rename(columns={"created_at": "retired_date"})

    collector_all = collector_all.merge(retired_events, left_on="id", right_on="collector_id", how="left")

    now = pd.Timestamp.now(tz="UTC")
    collector_all["age_days"] = (now - collector_all["in_service_date"]).dt.days
    collector_all["age_fmt"]  = collector_all["age_days"].apply(format_age)

    fleet_table = collector_all[[
        "store_name", "production_date", "in_service_date", "retired_date",
        "status", "age_fmt"
    ]].copy()
    fleet_table.columns = [
        "Location", "Production Date", "Active Since", "Retired Date", "Status", "Age"
    ]
    for col in ["Production Date", "Active Since", "Retired Date"]:
        fleet_table[col] = pd.to_datetime(fleet_table[col], utc=True, errors="coerce").dt.strftime("%b %d %Y")
    fleet_table["Retired Date"] = fleet_table["Retired Date"].fillna("—")

    # Deployments per month and year
    collector_all["deploy_month"] = collector_all["in_service_date"].dt.to_period("M").astype(str)
    collector_all["deploy_year"]  = collector_all["in_service_date"].dt.year.astype("Int64").astype(str)
    deployments_by_month = (collector_all.groupby("deploy_month").size()
                            .reset_index(name="cubes_deployed")
                            .sort_values("deploy_month"))
    deployments_by_year  = (collector_all.groupby("deploy_year").size()
                            .reset_index(name="cubes_deployed")
                            .sort_values("deploy_year"))

    # Retirements per year
    collector_all["retire_year"] = pd.to_datetime(
        collector_all["retired_date"], utc=True, errors="coerce").dt.year.astype("Int64").astype(str)
    retirements_by_year = (collector_all[collector_all["retired_date"].notna()]
                           .groupby("retire_year").size()
                           .reset_index(name="cubes_retired")
                           .sort_values("retire_year"))
    retired_cubes = collector_all[collector_all["retired_date"].notna()][
        ["store_name", "in_service_date", "retired_date"]].copy()
    retired_cubes.columns = ["Location", "Active Since", "Retired Date"]

    fleet_summary = {
        "total_ever":   len(collector_all),
        "total_active": len(collector_all[collector_all["status"].str.strip() == "Active"]),
        "total_retired":len(collector_all[collector_all["status"].str.strip() == "Retired"]),
        "avg_age_days": round(collector_all[collector_all["status"].str.strip() == "Active"]["age_days"].mean(), 0),
    }

    # ── Active cubes only from here ────────────────────────────
    collector = collector_all[
        (~collector_all["store_id"].isin(store_excluded)) &
        (collector_all["status"].str.strip() == "Active")
    ].copy()

    active_collector_ids = set(collector["id"].tolist())
    events  = events[events["collector_id"].isin(active_collector_ids)].copy()
    service = service[service["collector_id"].isin(active_collector_ids)].copy()
    events["event"] = events["event"].str.strip()

    # ── Sherpa profiles ────────────────────────────────────────
    sherpas = profile[profile["is_sherpa"] == True].copy()
    sherpas = sherpas[["user_id", "sherpa_rating"]] if "sherpa_rating" in sherpas.columns \
              else sherpas[["user_id"]]

    # ── Device OS breakdown ────────────────────────────────────
    def extract_os(val):
        if pd.isna(val) or str(val).strip() == "":
            return None
        try:
            d = json.loads(str(val).replace("'", '"'))
            os = d.get("os", "").strip().lower()
            return os if os else None
        except Exception:
            return None

    if "device_info" in profile.columns:
        profile["os"] = profile["device_info"].apply(extract_os)
        os_breakdown = (profile[profile["os"].notna()]
                        .groupby("os")["user_id"].nunique()
                        .reset_index(name="user_count")
                        .sort_values("user_count", ascending=False))
        os_breakdown["os"] = os_breakdown["os"].str.capitalize()
    else:
        os_breakdown = pd.DataFrame(columns=["os", "user_count"])

    # ── Completed services ─────────────────────────────────────
    finished = service[service["completion_date"].notna()].copy()
    finished["service_duration_hrs"] = (
        (finished["completion_date"] - finished["acceptation_date"])
        .dt.total_seconds() / 3600)
    finished["accept_lag_hrs"] = (
        (finished["acceptation_date"] - finished["created_at"])
        .dt.total_seconds() / 3600)

    # ── Q1: How long cube was full ─────────────────────────────
    finished["full_duration_raw"] = (
        (finished["completion_date"] - finished["created_at"])
        .dt.total_seconds() / 3600).clip(0, 168)
    finished["full_duration_ophrs"] = finished.apply(
        lambda r: operating_hours_overlap(r["created_at"], r["completion_date"]), axis=1)

    q1_full = (finished.merge(collector[["id", "store_name"]],
                              left_on="collector_id", right_on="id", how="left")
               .groupby(["collector_id", "store_name"])
               .agg(**{
                   "Avg Hrs Full incl overnight (service created → completion)": ("full_duration_raw", "mean"),
                   "Avg Hrs Full op hrs only (service created → completion)":    ("full_duration_ophrs", "mean"),
                   "Services": ("id_x", "count")
               })
               .reset_index()
               .sort_values("Avg Hrs Full incl overnight (service created → completion)", ascending=False)
               .head(10).round(1))

    # ── Q2: Maintenance transitions + hardware failures ────────
    maint_event_vals = ["maintenance", "needs-maintenance", "NeedsMaintenance"]
    events_sorted    = events.sort_values(["collector_id", "created_at"])
    events_sorted["prev_event"] = events_sorted.groupby("collector_id")["event"].shift(1)

    maint_transitions = events_sorted[
        events_sorted["event"].isin(maint_event_vals) &
        ~events_sorted["prev_event"].isin(maint_event_vals)
    ].copy()

    q2_freq = (maint_transitions.groupby("collector_id").size()
               .reset_index(name="maint_transitions")
               .merge(collector[["id", "store_name"]], left_on="collector_id", right_on="id", how="left")
               .sort_values("maint_transitions", ascending=False)
               .head(10))

    if "highest_priority_problem" in events.columns:
        hw_failures = events[events["highest_priority_problem"].notna() &
                             (events["highest_priority_problem"] != "")].copy()
        hw_failures = hw_failures.merge(collector[["id", "store_name"]],
                                        left_on="collector_id", right_on="id", how="left")
        q2_failures = (hw_failures.groupby(["store_name", "highest_priority_problem"])
                       .size().reset_index(name="count")
                       .sort_values("count", ascending=False).head(20))
    else:
        q2_failures = pd.DataFrame(columns=["store_name", "highest_priority_problem", "count"])

    # ── Q3: Maintenance duration ───────────────────────────────
    maint_start_df = maint_transitions[["collector_id", "created_at"]].rename(
        columns={"created_at": "maint_start"})
    ready_df = events[events["event"].isin(["ready", "Ready", "Finished", "StatusActive"])][
        ["collector_id", "created_at"]].rename(columns={"created_at": "maint_end"})

    maint_merged = maint_start_df.merge(ready_df, on="collector_id", how="left")
    maint_merged = maint_merged[maint_merged["maint_end"] > maint_merged["maint_start"]]
    maint_merged = (maint_merged.sort_values(["collector_id", "maint_start", "maint_end"])
                    .groupby(["collector_id", "maint_start"]).first().reset_index())
    maint_merged["maint_duration_raw"] = (
        (maint_merged["maint_end"] - maint_merged["maint_start"])
        .dt.total_seconds() / 3600).clip(0, 168)
    maint_merged["maint_duration_ophrs"] = maint_merged.apply(
        lambda r: operating_hours_overlap(r["maint_start"], r["maint_end"]), axis=1)

    q3_maint = (maint_merged.groupby("collector_id")
                .agg(**{
                    "Avg Hrs in Maint incl overnight (maint event → next ready)": ("maint_duration_raw", "mean"),
                    "Avg Hrs in Maint op hrs only (maint event → next ready)":    ("maint_duration_ophrs", "mean"),
                    "Maint Events": ("maint_start", "count")
                })
                .reset_index()
                .merge(collector[["id", "store_name"]], left_on="collector_id", right_on="id", how="left")
                .sort_values("Avg Hrs in Maint incl overnight (maint event → next ready)", ascending=False)
                .head(10).round(1))

    # ── Q4: Accept lag by cube ─────────────────────────────────
    finished_lag = finished[finished["accept_lag_hrs"].between(0, 48)].copy()
    q4_cube = (finished_lag.merge(collector[["id", "store_name"]],
                                  left_on="collector_id", right_on="id", how="left")
               .groupby(["collector_id", "store_name"])["accept_lag_hrs"]
               .mean().reset_index(name="Avg Hrs to Accept (service created → sherpa accepted)")
               .sort_values("Avg Hrs to Accept (service created → sherpa accepted)", ascending=False)
               .head(10).round(1))

    # ── Q5: Provider performance ───────────────────────────────
    cancel_event_vals = ["Cancelled", "Ready(ManualCancel)", "Ready(AutoCancel)",
                         "Ready(NoElegibleSherpaInPool)", "Ready (ManualCancel)", "Ready (AutoCancel)"]
    cancels       = events[events["event"].isin(cancel_event_vals)]
    cancel_counts = cancels.groupby("operator_id").size().reset_index(name="cancel_count")

    sherpa_services = finished.merge(sherpas, left_on="operator_id", right_on="user_id", how="inner")
    total_jobs      = sherpa_services.groupby("operator_id").size().reset_index(name="total_jobs")
    avg_duration    = (sherpa_services[sherpa_services["service_duration_hrs"].between(0, 24)]
                       .groupby("operator_id")["service_duration_hrs"]
                       .mean().reset_index(name="avg_duration_hrs"))

    q5_providers = (total_jobs
                    .merge(cancel_counts, on="operator_id", how="left")
                    .merge(avg_duration,  on="operator_id", how="left"))
    q5_providers["cancel_count"]    = q5_providers["cancel_count"].fillna(0)
    q5_providers["cancel_rate_pct"] = (q5_providers["cancel_count"] /
                                        q5_providers["total_jobs"] * 100).round(1)
    q5_providers["avg_duration_hrs"] = q5_providers["avg_duration_hrs"].round(1)

    q5_worst_cancel = (q5_providers[q5_providers["cancel_count"] > 0]
                       .sort_values("cancel_rate_pct", ascending=False).head(5))
    q5_top_volume   = q5_providers.sort_values("total_jobs", ascending=False).head(5)
    q5_top_speed    = q5_providers.sort_values("avg_duration_hrs", ascending=True).head(5)

    if "sherpa_rating" in sherpas.columns:
        flagged = sherpas[sherpas["sherpa_rating"] <= 0][["user_id", "sherpa_rating"]]
        flagged_in_service = flagged.merge(
            sherpa_services[["operator_id"]].drop_duplicates(),
            left_on="user_id", right_on="operator_id", how="inner")
    else:
        flagged_in_service = pd.DataFrame()

    timer_events = ["DEBUG-ExtendedServiceTimer", "Service Timer Extended"]
    q5_timers = (events[events["event"].isin(timer_events)]
                 .groupby("operator_id").size().reset_index(name="timer_extensions")
                 .merge(sherpas[["user_id"]], left_on="operator_id", right_on="user_id", how="inner")
                 .sort_values("timer_extensions", ascending=False).head(10))

    if "empty_cube" in service.columns:
        svc = service.copy()
        svc["service_type"] = svc["empty_cube"].apply(
            lambda x: "Cube Empty" if str(x).upper() in ["TRUE", "1"] else "CSD Pickup")
        q5_svc_type = svc.groupby("service_type").size().reset_index(name="count")
    else:
        q5_svc_type = pd.DataFrame()

   # ── New users since last snapshot ─────────────────────────
    # This gets computed in render using snapshot date
    # Store user join data for later use
    user_join_os = auth_user[["id", "date_joined"]].copy()
    if "device_info" in profile.columns:
        profile_os = profile[["user_id", "os"]].copy() if "os" in profile.columns else pd.DataFrame()
        if len(profile_os) > 0:
            user_join_os = user_join_os.merge(
                profile_os, left_on="id", right_on="user_id", how="left")
    new_users_summary = None

    # ── Q6: User cohorts + sessions ────────────────────────────
    data_start = deposit["date"].min() if len(deposit) > 0 else None
    data_end   = deposit["date"].max() if len(deposit) > 0 else None
    deposit["deposit_month"] = deposit["date"].dt.to_period("M").astype(str)
    q6_cohorts = (deposit.groupby("deposit_month")
                  .agg(total_deposits=("id", "count"),
                       unique_users=("depositor_id", "nunique"))
                  .reset_index()
                  .sort_values("deposit_month"))

    deposit_loc = deposit.merge(
        store[["id", "display_name"]].rename(columns={"id": "store_id", "display_name": "store_name"}),
        on="store_id", how="left")
    if "session_id" in deposit.columns:
        sessions = deposit_loc.groupby(["store_name", "session_id"]).size().reset_index(name="deposits_in_session")
        q6_sessions = (sessions.groupby("store_name")["deposits_in_session"]
                       .mean().reset_index(name="avg_deposits_per_session")
                       .sort_values("avg_deposits_per_session", ascending=False)
                       .head(10).round(1))
    else:
        q6_sessions = pd.DataFrame()

    # ── Q7: Cube engagement ────────────────────────────────────
    deposit_cube = deposit.merge(collector[["id", "store_name"]],
                                 left_on="collector_id", right_on="id", how="left")
    user_visits  = deposit_cube.groupby(["collector_id", "depositor_id"]).size().reset_index(name="visits")
    total_users  = user_visits.groupby("collector_id")["depositor_id"].nunique().reset_index(name="unique_users")
    return_users = (user_visits[user_visits["visits"] > 1]
                    .groupby("collector_id")["depositor_id"].nunique().reset_index(name="return_users"))
    q7_engagement = (total_users.merge(return_users, on="collector_id", how="left")
                     .merge(collector[["id", "store_name"]], left_on="collector_id", right_on="id", how="left"))
    q7_engagement["return_users"]   = q7_engagement["return_users"].fillna(0).astype(int)
    q7_engagement["return_rate_pct"] = (q7_engagement["return_users"] /
                                         q7_engagement["unique_users"] * 100).round(1)
    q7_engagement = q7_engagement.sort_values("unique_users", ascending=False).head(10)

    # ── Q8: Location retention ─────────────────────────────────
    user_store   = deposit.groupby(["depositor_id", "store_id"]).size().reset_index(name="visits")
    repeat_users = user_store[user_store["visits"] > 1]
    q8_retention = (repeat_users.groupby("store_id")["depositor_id"].nunique()
                    .reset_index(name="repeat_users")
                    .merge(store[["id", "display_name"]].rename(
                        columns={"id": "store_id", "display_name": "store_name"}),
                        on="store_id", how="left")
                    .sort_values("repeat_users", ascending=False).head(10))

    # ── Q9: Deposit volume + brands + container type ───────────
    q9_volume = (deposit_loc.groupby("store_name").size()
                 .reset_index(name="total_deposits")
                 .sort_values("total_deposits", ascending=False).head(10))
    q9_brands = (deposit.groupby("brand").size()
                 .reset_index(name="count")
                 .sort_values("count", ascending=False).head(10))
    if "type" in deposit.columns:
        q9_container = (deposit_loc.groupby(["store_name", "type"]).size()
                        .reset_index(name="count")
                        .sort_values("count", ascending=False))
    else:
        q9_container = pd.DataFrame()

   # ── Q10: CSD pickups ───────────────────────────────────────
    # Filter to completed dropoffs only (status = READY)
    csddropoff_ready = csddropoff[
        csddropoff["status"].str.upper().str.strip() == "READY"
    ].copy() if "status" in csddropoff.columns else csddropoff.copy()

    csd_merged = csddropoffbag.merge(
        csddropoff_ready[["id", "store_id", "collector_id", "depositor_id"]],
        left_on="csd_id", right_on="id", how="inner")
    csd_merged = csd_merged.merge(
        store[["id", "display_name"]].rename(columns={"id": "store_id", "display_name": "store_name"}),
        on="store_id", how="left")

    # Ensure numeric columns
    for col in ["small", "large"]:
        if col in csd_merged.columns:
            csd_merged[col] = pd.to_numeric(csd_merged[col], errors="coerce").fillna(0)
    csd_merged["total_containers"] = csd_merged["small"] + csd_merged["large"]

    # CSD by location
    q10_csd_location = (csd_merged.groupby("store_name").size()
                        .reset_index(name="bag_count")
                        .sort_values("bag_count", ascending=False).head(10))

    # CSD by material with small/large breakdown
    material_agg = (csd_merged.groupby("material")
                    .agg(small=("small", "sum"),
                         large=("large", "sum"),
                         total_containers=("total_containers", "sum"))
                    .reset_index()
                    .sort_values("total_containers", ascending=False))
    # BWN — all containers are large, rename for clarity
    material_agg.loc[material_agg["material"] == "BWN", "small"] = None
    material_agg = material_agg.rename(columns={"large": "large / BWN total"})
    q10_csd_material = material_agg

    # ── Top 10 CSD depositors (wide format) ───────────────────
    # Per depositor per material — small and large sums
    dep_mat = csd_merged.groupby(["depositor_id", "material"]).agg(
        small=("small", "sum"),
        large=("large", "sum")
    ).reset_index()

    # Pivot to wide format
    small_pivot = dep_mat.pivot(index="depositor_id", columns="material", values="small").fillna(0)
    large_pivot = dep_mat.pivot(index="depositor_id", columns="material", values="large").fillna(0)

    small_pivot.columns = [f"{col} Small" for col in small_pivot.columns]
    large_pivot.columns = [f"{col} Large" for col in large_pivot.columns]

    dep_wide = pd.concat([small_pivot, large_pivot], axis=1).reset_index()

    # Rename BWN columns — no size distinction
    for col in ["BWN Small", "BWN Large"]:
        if col in dep_wide.columns:
            dep_wide = dep_wide.rename(columns={col: "BWN Containers"})
    # If both BWN Small and Large exist, combine them
    if "BWN Containers" in dep_wide.columns and dep_wide.columns.tolist().count("BWN Containers") > 1:
        bwn_cols = [c for c in dep_wide.columns if c == "BWN Containers"]
        dep_wide["BWN Containers"] = dep_wide[bwn_cols].sum(axis=1)
        dep_wide = dep_wide.loc[:, ~dep_wide.columns.duplicated()]

    # Total bags and containers per depositor
    total_bags = (csd_merged.groupby("depositor_id").size().reset_index(name="Total Bags"))
    total_cont = (csd_merged.groupby("depositor_id")["total_containers"]
                  .sum().reset_index(name="Total Containers"))

    dep_wide = (dep_wide.merge(total_bags, on="depositor_id", how="left")
                        .merge(total_cont, on="depositor_id", how="left"))

    # Sort by total bags, keep top 10
    dep_wide = dep_wide.sort_values("Total Bags", ascending=False).head(10)

    # Reorder columns — depositor first, then totals, then materials
    material_cols = [c for c in dep_wide.columns
                     if c not in ["depositor_id", "Total Bags", "Total Containers"]]
    dep_wide = dep_wide[["depositor_id", "Total Bags"] + sorted(material_cols) + ["Total Containers"]]

    q10_csd_depositors = dep_wide

    # ── CSD vs maintenance correlation ─────────────────────────
    csd_by_store  = q10_csd_location.rename(columns={"bag_count": "csd_bags"})
    maint_by_store = (maint_transitions.merge(collector[["id", "store_name"]],
                                               left_on="collector_id", right_on="id", how="left")
                      .groupby("store_name").size().reset_index(name="maint_count"))
    csd_maint_corr = (csd_by_store.merge(maint_by_store, on="store_name", how="inner")
                      .sort_values("csd_bags", ascending=False).head(10))

    # ── Visual flags ───────────────────────────────────────────
    flags = {}
    if len(q1_full) > 0:
        worst_full = q1_full.iloc[0]
        flags["cube_full_longest"] = {
            "location": worst_full.get("store_name", "—"),
            "value": f"{worst_full['Avg Hrs Full incl overnight (service created → completion)']}h",
            "sub": "avg hours full (incl overnight)"
        }
    if len(q3_maint) > 0:
        worst_maint = q3_maint.iloc[0]
        flags["cube_maint_longest"] = {
            "location": worst_maint.get("store_name", "—"),
            "value": f"{worst_maint['Avg Hrs in Maint incl overnight (maint event → next ready)']}h",
            "sub": "avg hours in maintenance"
        }
    if len(q9_volume) > 0:
        top_vol = q9_volume.iloc[0]
        flags["top_deposit_cube"] = {
            "location": top_vol.get("store_name", "—"),
            "value": f"{top_vol['total_deposits']:,}",
            "sub": "total deposits"
        }
    if len(q7_engagement) > 0:
        top_eng = q7_engagement.iloc[0]
        flags["busiest_cube"] = {
            "location": top_eng.get("store_name", "—"),
            "value": str(top_eng["unique_users"]),
            "sub": f"unique users · {top_eng['return_rate_pct']}% return rate"
        }
    if len(q10_csd_location) > 0:
        top_csd = q10_csd_location.iloc[0]
        flags["max_csd_location"] = {
            "location": top_csd.get("store_name", "—"),
            "value": str(top_csd["bag_count"]),
            "sub": "CSD bags picked up"
        }
    if len(csd_maint_corr) > 0:
        top_corr = csd_maint_corr.iloc[0]
        flags["csd_maint_flag"] = {
            "location": top_corr.get("store_name", "—"),
            "value": f"{top_corr['csd_bags']} CSD / {top_corr['maint_count']} maint",
            "sub": "highest CSD + maintenance overlap"
        }

    # ── Summary metrics ────────────────────────────────────────
    summary = {
        "active_cubes":    len(active_collector_ids),
        "total_deposits":  len(deposit),
        "total_services":  len(finished),
        "avg_full_raw":    round(q1_full["Avg Hrs Full incl overnight (service created → completion)"].mean(), 1)
                           if len(q1_full) > 0 else 0,
        "avg_accept_lag":  round(q4_cube["Avg Hrs to Accept (service created → sherpa accepted)"].mean(), 1)
                           if len(q4_cube) > 0 else 0,
        "flagged_sherpas": len(flagged_in_service),
        "total_maint":     len(maint_transitions),
    }

    return {
        "summary":             summary,
        "flags":               flags,
        "fleet_table":         fleet_table,
        "fleet_summary":       fleet_summary,
        "deployments_by_month":deployments_by_month,
        "deployments_by_year": deployments_by_year,
        "retirements_by_year": retirements_by_year,
        "retired_cubes":       retired_cubes,
        "q1_full":             q1_full,
        "q2_freq":             q2_freq,
        "q2_failures":         q2_failures,
        "q3_maint":            q3_maint,
        "q4_cube":             q4_cube,
        "q5_worst_cancel":     q5_worst_cancel,
        "q5_top_volume":       q5_top_volume,
        "q5_top_speed":        q5_top_speed,
        "q5_timers":           q5_timers,
        "q5_svc_type":         q5_svc_type,
        "q5_flagged":          flagged_in_service,
        "os_breakdown":        os_breakdown,
        "new_users_summary":   new_users_summary,
        "user_join_os":        user_join_os,
        "q6_cohorts":          q6_cohorts,
        "q6_sessions":         q6_sessions,
        "q7_engagement":       q7_engagement,
        "q8_retention":        q8_retention,
        "q9_volume":           q9_volume,
        "q9_brands":           q9_brands,
        "q9_container":        q9_container,
        "q10_csd_location":    q10_csd_location,
        "q10_csd_material":    q10_csd_material,
        "q10_csd_depositors":  q10_csd_depositors,
        "csd_maint_corr":      csd_maint_corr,
        "data_start":          data_start,
        "data_end":            data_end,
    }

# ── Build prompt ───────────────────────────────────────────────
def build_prompt(metrics):
    def t(df): return df.to_string(index=False) if len(df) > 0 else "No data"
    return f"""
You are an operations analyst for Olyns, an AI-powered recycling platform.
Cubes = kiosks. Sherpas = service providers who empty and maintain Cubes.

Analyze the metrics below and write a structured operational briefing.
Be specific, use the numbers, flag anomalies clearly.

Your response must use these EXACT section markers:
=== CUBE PERFORMANCE ===
=== MAINTENANCE ALERTS ===
=== SERVICE RESPONSE TIME ===
=== PROVIDER PERFORMANCE ===
=== USER BEHAVIOR & DEPOSIT TRENDS ===
=== LOCATION PERFORMANCE ===
=== CSD BAG PICKUPS ===
=== ANOMALY FLAGS ===
=== TOP 3 RECOMMENDED ACTIONS ===

For each section write 2-4 sentences of sharp specific commentary.
For ANOMALY FLAGS list 3-5 anomalies as: ⚠️ [description with numbers]
For TOP 3 RECOMMENDED ACTIONS use:
ACTION 1: [title]
[explanation]
ACTION 2: [title]
[explanation]
ACTION 3: [title]
[explanation]

=== CUBE PERFORMANCE ===
How long cubes staying full, which worst, patterns.
{t(metrics["q1_full"])}

=== MAINTENANCE ALERTS ===
Maintenance frequency, hardware failures by cube, duration.
Transitions into maintenance:
{t(metrics["q2_freq"])}
Hardware failures by cube and type:
{t(metrics["q2_failures"])}
Maintenance duration:
{t(metrics["q3_maint"])}

=== SERVICE RESPONSE TIME ===
How long before sherpa accepts after service created.
{t(metrics["q4_cube"])}

=== PROVIDER PERFORMANCE ===
Worst cancellation rates:
{t(metrics["q5_worst_cancel"])}
Top by volume:
{t(metrics["q5_top_volume"])}
Top by speed:
{t(metrics["q5_top_speed"])}
Timer extensions:
{t(metrics["q5_timers"])}
Service type breakdown:
{t(metrics["q5_svc_type"])}
Flagged sherpas (zero/negative rating still active):
{t(metrics["q5_flagged"]) if len(metrics["q5_flagged"]) > 0 else "None"}

=== USER BEHAVIOR & DEPOSIT TRENDS ===
Cohort activity:
{t(metrics["q6_cohorts"])}
Avg deposits per session by location:
{t(metrics["q6_sessions"])}

=== LOCATION PERFORMANCE ===
Cube engagement (unique vs return users):
{t(metrics["q7_engagement"])}
Repeat users by location:
{t(metrics["q8_retention"])}
Deposit volume by location:
{t(metrics["q9_volume"])}
Top brands:
{t(metrics["q9_brands"])}

=== CSD BAG PICKUPS ===
By location:
{t(metrics["q10_csd_location"])}
By material:
{t(metrics["q10_csd_material"])}
CSD vs maintenance overlap:
{t(metrics["csd_maint_corr"])}
"""

# ── Comparison prompts ─────────────────────────────────────────
def build_wow_prompt(current, previous):
    def fmt(m):
        s = m.get("summary", {})
        return (f"Active cubes: {s.get('active_cubes')}, "
                f"Total deposits: {s.get('total_deposits')}, "
                f"Services: {s.get('total_services')}, "
                f"Avg full hrs: {s.get('avg_full_raw')}, "
                f"Avg accept lag: {s.get('avg_accept_lag')}, "
                f"Maintenance events: {s.get('total_maint')}, "
                f"Flagged sherpas: {s.get('flagged_sherpas')}")
    return f"""
You are an operations analyst for Olyns.
Compare these two weeks of operational data and write a concise week-over-week briefing.
For each metric clearly state: improved 🟢, declined 🔴, or stable 🟡.
End with 2-3 key takeaways.

Previous week ({previous.get('snapshot_date', 'unknown')}):
{fmt(previous)}

Current week:
{fmt(current)}
"""

def build_mom_prompt(snapshots_list):
    lines = []
    for s in snapshots_list:
        m = s.get("summary", {})
        lines.append(
            f"Week of {s.get('snapshot_date','unknown')}: "
            f"deposits={m.get('total_deposits')}, "
            f"services={m.get('total_services')}, "
            f"avg_full_hrs={m.get('avg_full_raw')}, "
            f"accept_lag={m.get('avg_accept_lag')}, "
            f"maint_events={m.get('total_maint')}")
    return f"""
You are an operations analyst for Olyns.
Analyze these weekly snapshots and write a recent changes briefing.
Do not include a title or heading. Start directly with KEY CHANGES.

Follow this exact format:

**KEY CHANGES**
• [metric name]: [one-line observation with specific numbers] [🟢 improving / 🔴 declining / 🟡 stable]
(write 4-5 bullets only — most important changes)

**ANALYSIS**
[2-3 short paragraphs. Be specific, use numbers. Under 120 words total. No filler phrases.]

Data:
{chr(10).join(lines)}
"""

def build_trend_prompt(snapshots_list):
    lines = []
    for s in snapshots_list:
        m = s.get("summary", {})
        lines.append(
            f"Week of {s.get('snapshot_date','unknown')}: "
            f"deposits={m.get('total_deposits')}, "
            f"services={m.get('total_services')}, "
            f"avg_full_hrs={m.get('avg_full_raw')}, "
            f"accept_lag={m.get('avg_accept_lag')}, "
            f"maint_events={m.get('total_maint')}")
    return f"""
You are an operations analyst for Olyns.
Analyze these {len(snapshots_list)} weeks of data and write a trend briefing.
Do not include a title or heading. Start directly with KEY TRENDS.

Follow this exact format:

**KEY TRENDS**
• [metric name]: [one-line trend observation with numbers] [🟢 / 🔴 / 🟡]
(write 4-5 bullets only)

**ANALYSIS**
[2-3 short paragraphs on patterns and persistent issues. Under 120 words total.]

**TOP 3 ACTIONS**
1. [action title]: [one sentence]
2. [action title]: [one sentence]
3. [action title]: [one sentence]

Data:
{chr(10).join(lines)}
"""

# ── Call Claude ────────────────────────────────────────────────
def call_claude(prompt, max_tokens=3000):
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

# ── Parse briefing sections ────────────────────────────────────
def parse_briefing(text):
    section_names = [
        "CUBE PERFORMANCE", "MAINTENANCE ALERTS", "SERVICE RESPONSE TIME",
        "PROVIDER PERFORMANCE", "USER BEHAVIOR & DEPOSIT TRENDS",
        "LOCATION PERFORMANCE", "CSD BAG PICKUPS", "ANOMALY FLAGS",
        "TOP 3 RECOMMENDED ACTIONS"
    ]
    sections = {}
    for i, name in enumerate(section_names):
        start_marker = f"=== {name} ==="
        end_marker   = f"=== {section_names[i+1]} ===" if i + 1 < len(section_names) else None
        start_idx    = text.find(start_marker)
        if start_idx == -1:
            sections[name] = ""
            continue
        start_idx += len(start_marker)
        end_idx = text.find(end_marker) if end_marker else len(text)
        sections[name] = text[start_idx:end_idx].strip()
    return sections

# ── Flag card helper ───────────────────────────────────────────
def flag_card(title, value, sub, color="blue"):
    return f"""
<div class="flag-card {color}">
    <div class="flag-title">{title}</div>
    <div class="flag-value">{value}</div>
    <div class="flag-sub">{sub}</div>
</div>"""

# ── Render briefing ────────────────────────────────────────────
def render_briefing(metrics, briefing_text, snapshots):
    s        = metrics["summary"]
    flags    = metrics["flags"]
    sections = parse_briefing(briefing_text)

    # ── Summary scorecard ──────────────────────────────────────
    st.markdown("### 📊 Summary Scorecard")
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    cards = [
        (c1, str(s["active_cubes"]),       "Active Cubes",        "blue"),
        (c2, f"{s['total_deposits']:,}",    "Total Deposits",      "green"),
        (c3, str(s["total_services"]),      "Services Completed",  "blue"),
        (c4, str(s["total_maint"]),         "Maint Transitions",   "orange" if s["total_maint"] > 20 else "green"),
        (c5, f"{s['avg_full_raw']}h",       "Avg Time Full",       "orange" if s["avg_full_raw"] > 8 else "green"),
        (c6, f"{s['avg_accept_lag']}h",     "Avg Accept Lag",      "orange" if s["avg_accept_lag"] > 2 else "green"),
        (c7, str(s["flagged_sherpas"]),     "Flagged Sherpas",     "red" if s["flagged_sherpas"] > 0 else "green"),
    ]
    for col, value, label, color in cards:
        with col:
            st.markdown(f"""
            <div class="metric-card {color}">
                <div class="value">{value}</div>
                <div class="label">{label}</div>
            </div>""", unsafe_allow_html=True)

    st.write("")

    # ── Visual flags ───────────────────────────────────────────
    st.markdown("### 🚩 Key Highlights")
    fc1, fc2, fc3 = st.columns(3)
    fc4, fc5, fc6 = st.columns(3)

    with fc1:
        if "cube_full_longest" in flags:
            f = flags["cube_full_longest"]
            st.markdown(flag_card("⏳ Cube Full Longest", f["value"], f["location"] + " · " + f["sub"], "red"),
                        unsafe_allow_html=True)
    with fc2:
        if "cube_maint_longest" in flags:
            f = flags["cube_maint_longest"]
            st.markdown(flag_card("🔧 In Maintenance Longest", f["value"], f["location"] + " · " + f["sub"], "orange"),
                        unsafe_allow_html=True)
    with fc3:
        if "top_deposit_cube" in flags:
            f = flags["top_deposit_cube"]
            st.markdown(flag_card("♻️ Top Cube by Deposits", f["value"], f["location"] + " · " + f["sub"], "green"),
                        unsafe_allow_html=True)
    with fc4:
        if "busiest_cube" in flags:
            f = flags["busiest_cube"]
            st.markdown(flag_card("👥 Busiest Cube by Users", f["value"], f["location"] + " · " + f["sub"], "green"),
                        unsafe_allow_html=True)
    with fc5:
        if "max_csd_location" in flags:
            f = flags["max_csd_location"]
            st.markdown(flag_card("📦 Max CSD Location", f["value"], f["location"] + " · " + f["sub"], "blue"),
                        unsafe_allow_html=True)
    with fc6:
        if "csd_maint_flag" in flags:
            f = flags["csd_maint_flag"]
            st.markdown(flag_card("⚠️ CSD + Maint Overlap", f["value"], f["location"] + " · " + f["sub"], "orange"),
                        unsafe_allow_html=True)

    st.write("")

    # ── Anomaly flags ──────────────────────────────────────────
    if sections.get("ANOMALY FLAGS"):
        st.markdown("### ⚠️ Anomaly Flags")
        for line in sections["ANOMALY FLAGS"].split("\n"):
            line = line.strip()
            if line:
                st.markdown(f'<div class="anomaly-box">{line}</div>', unsafe_allow_html=True)

    st.write("")

    # ── Top 3 actions ──────────────────────────────────────────
    if sections.get("TOP 3 RECOMMENDED ACTIONS"):
        st.markdown("### 🎯 Top 3 Recommended Actions")
        action_text = sections["TOP 3 RECOMMENDED ACTIONS"]
        for i in range(1, 4):
            marker      = f"ACTION {i}:"
            next_marker = f"ACTION {i+1}:" if i < 3 else None
            start       = action_text.find(marker)
            if start == -1:
                continue
            end        = action_text.find(next_marker) if next_marker else len(action_text)
            block      = action_text[start:end].strip()
            title_end  = block.find("\n")
            title      = block[len(marker):title_end].strip() if title_end > -1 else block[len(marker):].strip()
            body       = block[title_end:].strip() if title_end > -1 else ""
            st.markdown(f"""
            <div class="action-card">
                <div class="action-num">Action {i}</div>
                <div class="action-text"><strong>{title}</strong><br>{body}</div>
            </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Detailed sections ──────────────────────────────────────
    def t(df): return df

    section_config = [
        ("🏭 Cube Performance", "CUBE PERFORMANCE", [
            ("Cubes Staying Full Longest", metrics["q1_full"],
             ["store_name",
              "Avg Hrs Full incl overnight (service created → completion)",
              "Avg Hrs Full op hrs only (service created → completion)",
              "Services"]),
        ]),
        ("🔧 Maintenance Alerts", "MAINTENANCE ALERTS", [
            ("Maintenance Transitions per Cube", metrics["q2_freq"],
             ["store_name", "maint_transitions"]),
            ("Hardware Failures by Cube & Type", metrics["q2_failures"],
             ["store_name", "highest_priority_problem", "count"]),
            ("Maintenance Duration", metrics["q3_maint"],
             ["store_name",
              "Avg Hrs in Maint incl overnight (maint event → next ready)",
              "Avg Hrs in Maint op hrs only (maint event → next ready)",
              "Maint Events"]),
        ]),
        ("⏱️ Service Response Time", "SERVICE RESPONSE TIME", [
            ("Accept Lag by Cube", metrics["q4_cube"],
             ["store_name", "Avg Hrs to Accept (service created → sherpa accepted)"]),
        ]),
        ("🚗 Provider Performance", "PROVIDER PERFORMANCE", [
            ("Worst Cancellation Rates", metrics["q5_worst_cancel"],
             ["operator_id", "total_jobs", "cancel_count", "cancel_rate_pct"]),
            ("Top 5 by Volume", metrics["q5_top_volume"],
             ["operator_id", "total_jobs", "avg_duration_hrs"]),
            ("Top 5 by Speed", metrics["q5_top_speed"],
             ["operator_id", "avg_duration_hrs", "total_jobs"]),
            ("Timer Extensions", metrics["q5_timers"],
             ["operator_id", "timer_extensions"]),
            ("Service Type Breakdown", metrics["q5_svc_type"],
             ["service_type", "count"]),
        ]),
        ("👤 User Behavior & Deposits", "USER BEHAVIOR & DEPOSIT TRENDS", [
            ("iOS vs Android Users", metrics["os_breakdown"],
             ["os", "user_count"]),
            ("Cube Engagement — Unique vs Return Users", metrics["q7_engagement"],
             ["store_name", "unique_users", "return_users", "return_rate_pct"]),
            ("Deposits by Cohort Month", metrics["q6_cohorts"],
             ["cohort_month", "total_deposits", "unique_users"]),
            ("Avg Deposits per Session by Location", metrics["q6_sessions"],
             ["store_name", "avg_deposits_per_session"]),
        ]),
        ("📍 Location Performance", "LOCATION PERFORMANCE", [
            ("Repeat Users by Location", metrics["q8_retention"],
             ["store_name", "repeat_users"]),
            ("Deposit Volume by Location", metrics["q9_volume"],
             ["store_name", "total_deposits"]),
            ("Top Brands", metrics["q9_brands"],
             ["brand", "count"]),
        ]),
       ("♻️ CSD Bag Pickups", "CSD BAG PICKUPS", [
            ("Pickups by Location", metrics["q10_csd_location"],
             ["store_name", "bag_count"]),
            ("Pickups by Material (Small / Large / Total Containers)",
             metrics["q10_csd_material"],
             ["material", "small", "large / BWN total", "total_containers"]),
            ("Top 10 CSD Depositors", metrics["q10_csd_depositors"],
             [c for c in metrics["q10_csd_depositors"].columns]),
            ("CSD vs Maintenance Overlap by Location", metrics["csd_maint_corr"],
             ["store_name", "csd_bags", "maint_count"]),
        ]),
        ("🚛 Fleet Overview", None, [
            ("All Cubes — Active Since & Age", metrics["fleet_table"],
             ["Location", "Production Date", "Active Since", "Retired Date", "Status", "Age"]),
            ("Deployments by Month", metrics["deployments_by_month"],
             ["deploy_month", "cubes_deployed"]),
            ("Deployments by Year", metrics["deployments_by_year"],
             ["deploy_year", "cubes_deployed"]),
            ("Retirements by Year", metrics["retirements_by_year"],
             ["retire_year", "cubes_retired"]),
            ("Retired Cubes", metrics["retired_cubes"],
             ["Location", "Active Since", "Retired Date"]),
        ]),
    ]

    for section_title, section_key, tables in section_config:
        with st.expander(section_title, expanded=False):

            # ── New users since snapshot (User Behavior section only) ──
            if section_title == "👤 User Behavior & Deposits" and len(snapshots) >= 1:
                prev_snapshot = snapshots[-1]
                prev_date_str = prev_snapshot.get("snapshot_date", "unknown")
                try:
                    prev_date = pd.to_datetime(prev_date_str, utc=True)
                    user_join_os = metrics.get("user_join_os", pd.DataFrame())
                    if len(user_join_os) > 0 and "date_joined" in user_join_os.columns:
                        new_users = user_join_os[
                            user_join_os["date_joined"] > prev_date].copy()
                        total_new = len(new_users)
                        if "os" in new_users.columns:
                            os_new = (new_users[new_users["os"].notna()]
                                      .groupby("os")["id"].nunique()
                                      .reset_index(name="new_users"))
                            os_new["os"] = os_new["os"].str.capitalize()
                            os_lines = " · ".join(
                                f"{row['os']}: {row['new_users']}" 
                                for _, row in os_new.iterrows())
                        else:
                            os_lines = "OS breakdown unavailable"
                        st.markdown(f"""
                        <div class="flag-card green">
                            <div class="flag-title">👥 New Users Since {prev_date_str}</div>
                            <div class="flag-value">{total_new:,}</div>
                            <div class="flag-sub">{os_lines}</div>
                        </div>""", unsafe_allow_html=True)
                        st.write("")
                except Exception:
                    pass

            if section_key == "🚛 Fleet Overview":
                fs = metrics["fleet_summary"]
                fa, fb, fc, fd = st.columns(4)
                for col, val, lbl, clr in [
                    (fa, str(fs["total_ever"]),    "Total Ever Deployed", "blue"),
                    (fb, str(fs["total_active"]),  "Currently Active",    "green"),
                    (fc, str(fs["total_retired"]), "Retired",             "orange"),
                    (fd, format_age(fs["avg_age_days"]), "Avg Cube Age",  "blue"),
                ]:
                    with col:
                        st.markdown(f"""
                        <div class="metric-card {clr}">
                            <div class="value">{val}</div>
                            <div class="label">{lbl}</div>
                        </div>""", unsafe_allow_html=True)
                st.write("")

            if section_key and sections.get(section_key):
                st.markdown(f'<div class="commentary">{sections[section_key]}</div>',
                            unsafe_allow_html=True)
                st.write("")

            for table_title, df, cols in tables:
                if len(df) > 0:
                    st.markdown(f'<div class="section-header">{table_title}</div>',
                                unsafe_allow_html=True)
                    available = [c for c in cols if c in df.columns]
                    st.dataframe(df[available], use_container_width=True, hide_index=True)
                    st.write("")

    # ── Date label derived from actual data, not today's date ──
    data_start = metrics.get("data_start")
    data_end   = metrics.get("data_end")
    try:
        if data_start is not None and not pd.isna(data_start):
            snap_date_str   = f"{data_start.strftime('%Y-%m-%d')} to {data_end.strftime('%Y-%m-%d')}"
            snap_file_label = f"{data_start.strftime('%b%d').lower()}_{data_end.strftime('%b%d').lower()}"
        else:
            raise ValueError
    except Exception:
        snap_date_str   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        snap_file_label = snap_date_str

    # ── Week over week comparison ──────────────────────────────
    if len(snapshots) >= 1:
        st.divider()
        st.markdown("### 📈 Comparisons")
        current_snapshot = {
            "snapshot_date": snap_date_str,
            "summary": metrics["summary"]
        }
        previous = snapshots[-1]

        st.markdown("#### Week over Week")
        if "wow_text" not in st.session_state or st.session_state.wow_text is None:
            with st.spinner("Generating week-over-week comparison..."):
                st.session_state.wow_text = call_claude(
                    build_wow_prompt(current_snapshot, previous), max_tokens=1000)
        st.markdown(st.session_state.wow_text)

        if len(snapshots) >= 4:
            if st.button("📅 Generate Month over Month Analysis"):
                with st.spinner("Analyzing month over month..."):
                    all_snaps = snapshots + [current_snapshot]
                    st.session_state.mom_text = call_claude(
                        build_mom_prompt(all_snaps[-8:]), max_tokens=1500)
            if st.session_state.get("mom_text"):
                st.markdown("#### Month over Month")
                st.markdown(st.session_state.mom_text)

        if len(snapshots) >= 8:
            if st.button("📊 Generate 3-Month Trend Analysis"):
                with st.spinner("Analyzing 3-month trend..."):
                    all_snaps = snapshots + [current_snapshot]
                    st.session_state.trend_text = call_claude(
                        build_trend_prompt(all_snaps), max_tokens=2000)
            if st.session_state.get("trend_text"):
                st.markdown("#### 3-Month Trend")
                st.markdown(st.session_state.trend_text)

    # ── Save snapshot ──────────────────────────────────────────
    st.divider()
    st.markdown("### 💾 Save & Export")
    col_save, col_export = st.columns(2)

    with col_save:
        snapshot_data = {
            "snapshot_date": snap_date_str,
            "summary": metrics["summary"]
        }
        st.download_button(
            label="💾 Save Snapshot (for future comparisons)",
            data=json.dumps(snapshot_data, indent=2),
            file_name=f"olyns_snapshot_{snap_file_label}.json",
            mime="application/json"
        )

    with col_export:
        st.download_button(
            label="⬇️ Download Briefing as Text",
            data=briefing_text,
            file_name="olyns_operational_briefing.txt",
            mime="text/plain"
        )

# ── Tab 1: Generate Briefing ─────────────────────────────────────
with tab1:
    st.subheader("📁 Upload Data Files")
    st.markdown("Select all 10 CSV files at once — the app will detect each one automatically by filename.")
    st.markdown("""
<div class="upload-note">
📁 <strong>Files to be uploaded:</strong>
auth_user.csv · api_profile.csv · api_collector.csv · api_store.csv · api_company.csv ·
api_systemeventalert.csv · api_deposit.csv · api_olynsservice.csv · api_csddropoff.csv · api_csddropoffbag.csv
</div>
""", unsafe_allow_html=True)

    st.write("")
    uploaded_files = st.file_uploader(
        "Drop all 10 CSV files here",
        type="csv",
        accept_multiple_files=True,
        key="csv_upload"
    )

    filename_map = {
        "auth_user.csv":            "auth_user",
        "api_profile.csv":          "api_profile",
        "api_collector.csv":        "api_collector",
        "api_store.csv":            "api_store",
        "api_company.csv":          "api_company",
        "api_systemeventalert.csv": "api_systemevent",
        "api_deposit.csv":          "api_deposit",
        "api_olynsservice.csv":     "api_service",
        "api_csddropoff.csv":       "api_csddropoff",
        "api_csddropoffbag.csv":    "api_csddropoffbag",
    }

    uploads = {key: None for key in filename_map.values()}
    unrecognized = []
    for f in (uploaded_files or []):
        normalized = normalize_filename(f.name)
        if normalized in filename_map:
            uploads[filename_map[normalized]] = f
        elif f.name in filename_map:
            uploads[filename_map[f.name]] = f
        else:
            unrecognized.append(f.name)

    uploaded_count = sum(1 for f in uploads.values() if f is not None)
    missing = [name for name, key in filename_map.items() if uploads[key] is None]

    if unrecognized:
        st.warning(f"⚠️ Unrecognized files (ignored): {', '.join(unrecognized)}")
    if uploaded_count == 10:
        st.success("✅ All 10 files detected. Ready to generate briefing.")
    elif uploaded_count > 0:
        st.info(f"📂 {uploaded_count}/10 files detected. Still waiting for: {', '.join(missing)}")

    # ── Demo option ───────────────────────────────────────────────
    st.write("")
    st.markdown("**Don't have the data files? Try the demo.**")
    if st.button("🎬 Try Demo", key="demo_tab1_btn", help="Load sample data and generate a demo briefing"):
        with st.spinner("Loading demo — calling Claude with sample data..."):
            try:
                demo_m = get_demo_metrics()
                st.session_state.metrics       = demo_m
                st.session_state.briefing_text = call_claude(build_prompt(demo_m))
                st.session_state.demo_mode     = True
                for _key in ["wow_text", "mom_text", "trend_text"]:
                    st.session_state.pop(_key, None)
            except Exception as e:
                st.error(f"Demo failed: {e}")

    st.divider()
    st.subheader("🧠 Generate Briefing")
    run_button = st.button(
        "Generate Briefing",
        disabled=(uploaded_count < 10),
        type="primary",
        key="run_briefing_btn"
    )

    for _key in ["metrics", "briefing_text", "demo_mode"]:
        if _key not in st.session_state:
            st.session_state[_key] = None

    if run_button:
        with st.spinner("⏳ Processing data and generating briefing — this takes about 30 seconds..."):
            try:
                st.session_state.metrics       = process_data(uploads)
                st.session_state.briefing_text = call_claude(build_prompt(st.session_state.metrics))
                st.session_state.demo_mode     = False
                for _key in ["wow_text", "mom_text", "trend_text"]:
                    st.session_state.pop(_key, None)
            except Exception as e:
                st.error(f"Something went wrong: {e}")
                st.exception(e)

    if st.session_state.get("metrics") is not None:
        if st.session_state.get("demo_mode"):
            st.info("🎬 **Demo mode** — sample data only. Upload your own CSV files and click Generate Briefing to see a real briefing.")
        st.divider()
        st.subheader("📋 Operational Briefing")
        render_briefing(
            st.session_state.metrics,
            st.session_state.briefing_text,
            []
        )
        st.divider()
        if not st.session_state.get("demo_mode"):
            st.info("💡 **Next step:** Click **💾 Save Snapshot** above to download your snapshot file, then open the **Trend Analysis** tab to compare across weeks.")

# ── Tab 2: Trend Analysis ─────────────────────────────────────────
with tab2:
    st.markdown("""
<div class="upload-note">
📌 <strong>How this works:</strong> Each week, go to the <strong>Generate Briefing</strong> tab, upload your CSVs, and click <strong>💾 Save Snapshot</strong> at the bottom of the briefing. Upload those saved snapshot files here to compare across weeks.<br><br>
You need <strong>at least 2 snapshots</strong> to see the comparison table. Upload <strong>4 or more</strong> to unlock Trend Over Time.
</div>
""", unsafe_allow_html=True)

    st.write("")
    st.markdown("**Don't have snapshots yet? Try the demo.**")
    if "demo_snapshots" not in st.session_state:
        st.session_state.demo_snapshots = False
    if st.button("🎬 Try Demo", key="demo_tab2_btn", help="Load 6 weeks of sample snapshots"):
        st.session_state.demo_snapshots = True
        for _key in ["snap_only_mom", "snap_only_trend"]:
            st.session_state.pop(_key, None)

    st.write("")
    snapshot_files = st.file_uploader(
        "Upload your saved snapshot JSON files here",
        type="json",
        accept_multiple_files=True,
        key="snapshot_upload"
    )

    raw_snapshots = []
    for sf in (snapshot_files or []):
        try:
            data = json.load(sf)
            raw_snapshots.append(data)
        except Exception:
            st.warning(f"Could not read snapshot: {sf.name}")

    if len(raw_snapshots) > 0:
        st.session_state.demo_snapshots = False
        snapshots = sorted(raw_snapshots, key=lambda x: x.get("snapshot_date", ""))
    elif st.session_state.demo_snapshots:
        snapshots = DEMO_SNAPSHOTS
    else:
        snapshots = []

    if st.session_state.demo_snapshots:
        st.info("🎬 **Demo mode** — showing 6 weeks of sample data. Upload your own snapshot files above to replace this.")

    if len(snapshots) == 1:
        st.caption("1 snapshot uploaded — upload at least 1 more to see the comparison table.")

    if len(snapshots) >= 2:
        st.divider()
        n = len(snapshots)
        trend_note = "Trend Over Time: available" if n >= 4 else f"Trend Over Time: upload {4 - n} more snapshot(s) to unlock"
        st.caption(f"{n} snapshots loaded · {trend_note}")

        # ── Overview table ────────────────────────────────────
        st.markdown("##### Overview")
        snap_rows = []
        for s in snapshots:
            m = s.get("summary", {})
            snap_rows.append({
                "Week": s.get("snapshot_date", "?"),
                "Deposits": m.get("total_deposits", ""),
                "Services": m.get("total_services", ""),
                "Avg Hrs Full": m.get("avg_full_raw", ""),
                "Avg Accept Lag": m.get("avg_accept_lag", ""),
                "Maint Events": m.get("total_maint", ""),
                "Flagged Sherpas": m.get("flagged_sherpas", ""),
            })
        st.dataframe(pd.DataFrame(snap_rows), use_container_width=True, hide_index=True)

        # ── What changed ──────────────────────────────────────
        prev_s = snapshots[-2]
        curr_s = snapshots[-1]
        prev_date = prev_s.get("snapshot_date", "?")
        curr_date = curr_s.get("snapshot_date", "?")
        st.markdown(f"##### What changed? ({prev_date} vs {curr_date})")
        if n > 2:
            st.caption("Comparing your 2 most recent snapshots. Older ones feed into Recent Changes and Trend Over Time below.")
        prev_m = prev_s.get("summary", {})
        curr_m = curr_s.get("summary", {})

        wow_rows = []
        for label, key, better in [
            ("Total Deposits",        "total_deposits",  "higher"),
            ("Services Completed",    "total_services",  "higher"),
            ("Avg Hrs Cube Full",     "avg_full_raw",    "lower"),
            ("Avg Accept Lag (hrs)",  "avg_accept_lag",  "lower"),
            ("Maintenance Events",    "total_maint",     "lower"),
            ("Flagged Sherpas",       "flagged_sherpas", "lower"),
        ]:
            pv = prev_m.get(key)
            cv = curr_m.get(key)
            try:
                delta = float(cv) - float(pv)
                if delta == 0:
                    change = "→ No change"
                elif (better == "higher" and delta > 0) or (better == "lower" and delta < 0):
                    change = f"🟢 {'↑' if delta > 0 else '↓'} {abs(delta):.1f}"
                else:
                    change = f"🔴 {'↑' if delta > 0 else '↓'} {abs(delta):.1f}"
            except Exception:
                change = ""
            wow_rows.append({
                "Metric": label,
                f"Prev ({prev_s.get('snapshot_date','?')})": pv,
                f"Current ({curr_s.get('snapshot_date','?')})": cv,
                "Change": change,
            })
        st.dataframe(pd.DataFrame(wow_rows), use_container_width=True, hide_index=True)

        st.write("")

        # ── Recent Changes ────────────────────────────────────
        mom_done = bool(st.session_state.get("snap_only_mom"))
        st.markdown("**📊 Recent Changes** — AI summary of what improved or declined across your recent snapshots.")
        if st.button("Generate Recent Changes →", key="snap_only_mom_btn", disabled=mom_done):
            with st.spinner("Analyzing recent changes..."):
                st.session_state.snap_only_mom = call_claude(
                    build_mom_prompt(snapshots[-8:]), max_tokens=1000)
        if mom_done:
            st.caption("Analysis already generated — results below. Refresh the page to re-run.")
        if st.session_state.get("snap_only_mom"):
            st.markdown(st.session_state.snap_only_mom)

        st.write("")

        # ── Trend Over Time ───────────────────────────────────
        trend_disabled = n < 4
        trend_done = bool(st.session_state.get("snap_only_trend"))
        if trend_disabled:
            st.markdown(f"**📈 Trend Over Time** — AI analysis of patterns across all your snapshots. _(needs {4 - n} more snapshot(s) to unlock)_")
        else:
            st.markdown("**📈 Trend Over Time** — AI analysis of patterns across all your uploaded snapshots.")
        if st.button("Generate Trend Over Time →", key="snap_only_trend_btn", disabled=(trend_disabled or trend_done)):
            with st.spinner("Analyzing trend over time..."):
                st.session_state.snap_only_trend = call_claude(
                    build_trend_prompt(snapshots), max_tokens=1500)
        if trend_done:
            st.caption("Analysis already generated — results below. Refresh the page to re-run.")
        if st.session_state.get("snap_only_trend"):
            st.markdown(st.session_state.snap_only_trend)