import json
import glob
import os
import re
import pandas as pd
import numpy as np
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

# Config
st.set_page_config(
    page_title="Election Dashboard — เขต 6 เชียงใหม่",
    page_icon=None,
    layout="wide",
)

PARTY_COLORS = {
    "ประชาชน":           "#FF6413",
    "ก้าวไกล":           "#EF771E",
    "ประชาชน/ก้าวไกล":  "#FF6413",
    "เพื่อไทย":          "#CC0000",
    "ภูมิใจไทย":         "#312682",
    "รวมไทยสร้างชาติ":   "#121F91",
    "ประชาธิปัตย์":      "#15A5F5",
    "กล้าธรรม" : "#4EC86F"
}
DEFAULT_COLOR = "#78909C"

# filename (lowercase) -> amphoe name
# parsed from filename: อำเภอXXX_ss.json -> XXX
# nokhet = out-of-district unit (no tambon, party-list only)
NOKHET_KEY = "nokhet"

PARTY_NAMES = [
    "ไทยทรัพย์ทวี","เพื่อชาติไทย","ใหม่","มิติใหม่","รวมใจไทย",
    "รวมไทยสร้างชาติ","พลวัต","ประชาธิปไตยใหม่","เพื่อไทย","ทางเลือกใหม่",
    "เศรษฐกิจ","เสรีรวมไทย","รวมพลังประชาชน","ท้องที่ไทย","อนาคตไทย",
    "พลังเพื่อไทย","ไทยชนะ","พลังสังคมใหม่","สังคมประชาธิปไตยไทย","ฟิวชัน",
    "ไทรวมพลัง","ก้าวอิสระ","ปวงชนไทย","วิชชั่นใหม่","เพื่อชีวิตใหม่",
    "คลองไทย","ประชาธิปัตย์","ไทยก้าวหน้า","ไทยภักดี","แรงงานสร้างชาติ",
    "ประชากรไทย","ครูไทยเพื่อประชาชน","ประชาชาติ","สร้างอนาคตไทย","รักชาติ",
    "ไทยพร้อม","ภูมิใจไทย","พลังธรรมใหม่","กรีน","ไทยธรรม",
    "แผ่นดินธรรม","กล้าธรรม","พลังประชารัฐ","โอกาสใหม่","เป็นธรรม",
    "ประชาชน","ประชาไทย","ไทยสร้างไทย","ไทยก้าวใหม่","ประชาอาสาชาติ",
    "พร้อม","เครือข่ายชาวนาแห่งประเทศไทย","ไทยพิทักษ์ธรรม","ความหวังใหม่",
    "ไทยรวมไทย","เพื่อบ้านเมือง","พลังไทยรักชาติ",
]

PARTY_NAME_FIX = {
    "วิชช์ชื่นใหม่": "วิชชั่นใหม่",
    "วิชช์นใหม่":    "วิชชั่นใหม่",
    "วิชช์ชั่นใหม่": "วิชชั่นใหม่",
    "วิชชันใหม่":    "วิชชั่นใหม่",
    "วิชช่นใหม่":    "วิชชั่นใหม่",
    "วิชช์นิ่มใหม่": "วิชชั่นใหม่",
    "วิชช์ซันใหม่":  "วิชชั่นใหม่",
    "วิชช์ใหม่":     "วิชชั่นใหม่",
}

# Helpers
def party_color(name):
    return PARTY_COLORS.get(name, DEFAULT_COLOR)

def amphoe_from_filename(path: str) -> str:
    """
    อำเภอเชียงดาว_ss.json          ->  เชียงดาว
    อำเภอเชียงดาว_confidence.json  ->  เชียงดาว
    nokhet_ss.json                  ->  nokhet  (นอกเขต ไม่มีตำบล)
    """
    base = os.path.basename(path)
        # primary pattern: อำเภอXXX_anything.json
    m = re.match(r"^อำเภอ(.+?)_.*\.json$", base, re.IGNORECASE)
    if m:
        return m.group(1)
    # nokhet and other fallbacks
    return re.sub(r"_.*\.json$|\.json$", "", base, flags=re.IGNORECASE)

# ML helpers (Section 4) — see modeling.py
from modeling import (
    compute_concentration,
    compute_clustering,
    compute_anomaly,
    compute_regression,
)

# Data loading
@st.cache_data
def load_data():

    def flatten_election_data(json_data, election_type, amphoe=""):
        """แปลง JSON -> (df_summary, df_votes)"""
        summary_rows, vote_rows = [], []
        for tambon, units in json_data.items():
            for unit_name, unit_data in units.items():
                summary = unit_data.get("ballot_summary", {})
                # normalize combined unit names
                _unit = unit_name
                _cm = re.match(r"^combined_(\d+)$", str(_unit), re.IGNORECASE)
                if _cm:
                    _unit = f"รวม {_cm.group(1)} หน่วย"
                # normalize empty tambon values
                _tambon = "ไม่ระบุ" if (not tambon or str(tambon).strip() in ("-","","nan")) else tambon

                summary_rows.append({
                    "amphoe": amphoe, "tambon": _tambon, "unit": _unit,
                    "type": election_type,
                    "trusted_total":    unit_data.get("trusted_total"),
                    "ballots_used":     summary.get("ballots_used"),
                    "ballots_valid":    summary.get("ballots_valid"),
                    "ballots_spoiled":  summary.get("ballots_spoiled"),
                    "ballots_no_vote":  summary.get("ballots_no_vote"),
                    "is_manual_edited": unit_data.get("manual_edited", False),
                })
                for cid, votes in unit_data.get("votes", {}).items():
                    vote_rows.append({
                        "amphoe": amphoe, "tambon": _tambon, "unit": _unit,
                        "type": election_type,
                        "candidate_party_no": cid,
                        "votes": int(votes),
                    })
        df_summary = pd.DataFrame(summary_rows)
        df_votes   = pd.DataFrame(vote_rows)
        # dedup: sum votes for duplicate entries
        if not df_votes.empty:
            df_votes = (
                df_votes
                .groupby(["amphoe","tambon","unit","type","candidate_party_no"], sort=False)
                .agg(votes=("votes","sum"))
                .reset_index()
            )
        return df_summary, df_votes

    # scan all JSON files in data/final/
    # _ss.json = constituency, _confidence.json = party-list


    _all_json = sorted(glob.glob("data/final/*.json"))
    ss_files    = [f for f in _all_json if re.search(r"_ss\.json$", os.path.basename(f), re.IGNORECASE)]
    party_files = [f for f in _all_json if re.search(r"_confidence\.json$", os.path.basename(f), re.IGNORECASE)]

    all_summary, all_votes   = [], []
    all_dim_constituency     = []

    df_dim_party_list = pd.DataFrame({
        "type": "ปาร์ตี้ลิสต์",
        "candidate_party_no": [str(i) for i in range(1, len(PARTY_NAMES)+1)],
        "party_name":    PARTY_NAMES,
        "candidate_name": [""] * len(PARTY_NAMES),
        "amphoe": [""] * len(PARTY_NAMES),
    })

    # load constituency files (_ss)
    for path in ss_files:
        amphoe = amphoe_from_filename(path)
        with open(path, encoding="utf-8") as f:
            data_person = json.load(f)
        df_s, df_v = flatten_election_data(data_person, "เขต", amphoe)
        all_summary.append(df_s)
        all_votes.append(df_v)

        dim_rows = []
        for tambon, units in data_person.items():
            for unit_name, unit_data in units.items():
                for cand_no, info in unit_data.get("candidate_info", {}).items():
                    dim_rows.append({
                        "type": "เขต",
                        "candidate_party_no": str(cand_no),
                        "candidate_name": info["name"],
                        "party_name": PARTY_NAME_FIX.get(info["party"], info["party"]),
                        "amphoe": amphoe,
                    })
        if dim_rows:
            df_dim_c = pd.DataFrame(dim_rows)
            # dedup: keep first row per (amphoe, candidate_party_no)
            df_dim_c = (
                df_dim_c
                .groupby(["type","candidate_party_no","amphoe"], sort=False)
                .first()
                .reset_index()
            )
            all_dim_constituency.append(df_dim_c)

    # load party-list files
    for path in party_files:
        amphoe = amphoe_from_filename(path)
        with open(path, encoding="utf-8") as f:
            data_party = json.load(f)
        df_s, df_v = flatten_election_data(data_party, "ปาร์ตี้ลิสต์", amphoe)
        all_summary.append(df_s)
        all_votes.append(df_v)

    df_all_summary = pd.concat(all_summary, ignore_index=True) if all_summary else pd.DataFrame()
    df_all_votes   = pd.concat(all_votes,   ignore_index=True) if all_votes   else pd.DataFrame()

    df_dim_constituency = (
        pd.concat(all_dim_constituency, ignore_index=True)
        if all_dim_constituency else pd.DataFrame()
    )
    df_all_dim = pd.concat([df_dim_constituency, df_dim_party_list], ignore_index=True)

    df_all_votes["candidate_party_no"] = df_all_votes["candidate_party_no"].astype(str)

    # join constituency: include amphoe to avoid name collisions
    df_votes_ss = df_all_votes[df_all_votes["type"] == "เขต"]
    df_votes_pl = df_all_votes[df_all_votes["type"] == "ปาร์ตี้ลิสต์"]

    df_report_ss = pd.merge(
        df_votes_ss,
        df_dim_constituency[["type","candidate_party_no","amphoe","party_name","candidate_name"]],
        on=["type","candidate_party_no","amphoe"], how="left",
    )
    # party-list: join on type + candidate_party_no only (no amphoe in dim)
    df_report_pl = pd.merge(
        df_votes_pl,
        df_dim_party_list[["type","candidate_party_no","party_name","candidate_name"]],
        on=["type","candidate_party_no"], how="left",
    )

    df_final_report = pd.concat([df_report_ss, df_report_pl], ignore_index=True)
    df_final_report["party_name"] = df_final_report["party_name"].replace(PARTY_NAME_FIX)

    # load 2566 election data
    df_election = pd.read_csv("data/final/election_scores_2566.csv")
    df_location = pd.read_csv("data/final/election_locations_66.csv")

    df_cm6_election = df_election[
        (df_election["province"] == "เชียงใหม่") &
        (df_election["province_number"] == 6)
    ].copy()
    df_cm6_location = df_location[
        (df_location["provincename"] == "จังหวัดเชียงใหม่") &
        (df_location["divisionnumber"] == 6)
    ].copy()
    df_final_cm6 = pd.merge(
        df_cm6_election,
        df_cm6_location[["districtname","subdistrictname","lat_changable","lng_changable"]],
        left_on=["district","subdistrict"],
        right_on=["districtname","subdistrictname"],
        how="left",
    ).drop(columns=["districtname","subdistrictname"])
    df_final_cm6 = df_final_cm6.dropna(axis=1, how="all")

    # match tambons by loaded amphoe
    loaded_amphoe = df_final_report["amphoe"].dropna().unique().tolist()
    # exclude empty values and nokhet (no tambon, cannot match 66)
    loaded_amphoe = [a for a in loaded_amphoe if a and a != NOKHET_KEY]

    # normalize invalid tambon values
    df_final_report["tambon"] = df_final_report["tambon"].apply(
        lambda t: "ไม่ระบุ" if (pd.isna(t) or str(t).strip() in ("-","","nan")) else t
    )

    # filter to valid tambons for 66 matching
    df_69_for_match = df_final_report[
        (df_final_report["tambon"] != "ไม่ระบุ") &
        (df_final_report["amphoe"].isin(loaded_amphoe))
    ]
    set_69 = set(
        df_69_for_match["tambon"].str.replace("ตำบล","").str.strip().dropna()
    )
    df_66_t = (
        df_final_cm6[df_final_cm6["district"].isin(loaded_amphoe)]
        [["subdistrict"]].dropna().drop_duplicates()
    )
    set_66  = set(df_66_t["subdistrict"].str.strip())
    matched = set_69 & set_66

    # party vote columns from 66 dataset
    party_cols = [c for c in df_final_cm6.columns
                  if c.startswith("บช_")
                  and c not in ["บช_บัตรเสีย","บช_ผู้มาใช้สิทธิ์","บช_ผู้มีสิทธิ์","บช_ไม่เลือกผู้ใด"]]

    # aggregate 69 votes by tambon
    df_69_by_tambon = df_final_report[df_final_report["type"]=="เขต"].copy()
    df_69_by_tambon["tambon_key"] = df_69_by_tambon["tambon"].str.replace("ตำบล","").str.strip()
    df_69_by_tambon = df_69_by_tambon[df_69_by_tambon["tambon_key"].isin(matched)]
    df_69_by_tambon["party_name"] = df_69_by_tambon["party_name"].replace(PARTY_NAME_FIX)
    df_69_agg = (
        df_69_by_tambon
        .groupby(["tambon_key","party_name"])["votes"].sum()
        .reset_index()
        .rename(columns={"votes":"votes_69"})
    )

    # aggregate 66 votes by tambon
    df_66_long = (
        df_final_cm6[df_final_cm6["district"].isin(loaded_amphoe)]
        [["subdistrict"] + party_cols].copy()
    )
    df_66_long = df_66_long[df_66_long["subdistrict"].isin(matched)]
    df_66_long = df_66_long.melt(
        id_vars="subdistrict", value_vars=party_cols,
        var_name="party_name", value_name="votes_66"
    )
    df_66_long["party_name"] = df_66_long["party_name"].str.replace("บช_","")
    df_66_long = df_66_long.rename(columns={"subdistrict":"tambon_key"})
    df_66_agg  = df_66_long.groupby(["tambon_key","party_name"])["votes_66"].sum().reset_index()

    df_compare = pd.merge(df_69_agg, df_66_agg, on=["tambon_key","party_name"], how="inner")
    df_compare["vote_swing"] = df_compare["votes_69"] - df_compare["votes_66"]

    # merge ก้าวไกล + ประชาชน -> ประชาชน/ก้าวไกล for 66 vs 69 comparison
    # map each side separately so both elections combine correctly
    KP = {"ก้าวไกล": "ประชาชน/ก้าวไกล", "ประชาชน": "ประชาชน/ก้าวไกล"}

    df_69_kp = df_69_agg.copy()
    df_69_kp["party_name"] = df_69_kp["party_name"].replace(KP)
    df_69_kp = df_69_kp.groupby(["tambon_key","party_name"])["votes_69"].sum().reset_index()

    df_66_kp = df_66_agg.copy()
    df_66_kp["party_name"] = df_66_kp["party_name"].replace(KP)
    df_66_kp = df_66_kp.groupby(["tambon_key","party_name"])["votes_66"].sum().reset_index()

    df_compare_kp = pd.merge(df_69_kp, df_66_kp, on=["tambon_key","party_name"], how="outer").fillna(0)
    df_compare_kp["vote_swing"] = df_compare_kp["votes_69"] - df_compare_kp["votes_66"]

    # compute vote share (using kp-merged version)
    df_69_share = df_compare_kp.copy()
    df_69_share["total_69"] = df_69_share.groupby("tambon_key")["votes_69"].transform("sum")
    df_69_share["share_69"] = df_69_share["votes_69"] / df_69_share["total_69"] * 100
    df_69_share["total_66"] = df_69_share.groupby("tambon_key")["votes_66"].transform("sum")
    df_69_share["share_66"] = df_69_share["votes_66"] / df_69_share["total_66"] * 100
    df_69_share["share_swing"] = df_69_share["share_69"] - df_69_share["share_66"]

    # compute winners per tambon
    winner_69 = (
        df_compare_kp
        .loc[df_compare_kp.groupby("tambon_key")["votes_69"].idxmax()]
        [["tambon_key","party_name","votes_69"]]
        .rename(columns={"party_name":"winner_69"})
    )
    winner_66 = (
        df_compare_kp
        .loc[df_compare_kp.groupby("tambon_key")["votes_66"].idxmax()]
        [["tambon_key","party_name","votes_66"]]
        .rename(columns={"party_name":"winner_66"})
    )

    # merge geo coordinates
    df_geo = (
        df_final_cm6[df_final_cm6["district"].isin(loaded_amphoe)]
        [["subdistrict","lat_changable","lng_changable"]]
        .dropna().drop_duplicates("subdistrict")
    )
    df_map = df_geo.merge(winner_69, left_on="subdistrict", right_on="tambon_key", how="inner")
    df_map = df_map.merge(winner_66[["tambon_key","winner_66"]], on="tambon_key", how="left")
    df_map["flipped"] = df_map["winner_69"] != df_map["winner_66"]

    # compute turnout for 66 and 69
    df_t69_raw = df_all_summary[df_all_summary["type"]=="ปาร์ตี้ลิสต์"].copy()
    df_t69_raw["tambon_key"] = df_t69_raw["tambon"].str.replace("ตำบล","").str.strip()
    df_t69_raw = df_t69_raw[df_t69_raw["tambon_key"].isin(matched)]
    df_t69 = (
        df_t69_raw
        .groupby("tambon_key")
        .agg(eligible_69=("trusted_total","sum"), used_69=("ballots_used","sum"))
        .reset_index()
    )
    df_t69["turnout_rate_69"] = df_t69["used_69"] / df_t69["eligible_69"].where(df_t69["eligible_69"] > 0) * 100

    df_t66_raw = (
        df_final_cm6[df_final_cm6["district"].isin(loaded_amphoe)]
        [["subdistrict","บช_ผู้มีสิทธิ์","บช_ผู้มาใช้สิทธิ์"]].copy()
    )
    df_t66_raw = df_t66_raw[df_t66_raw["subdistrict"].isin(matched)].dropna()
    df_t66 = (
        df_t66_raw
        .groupby("subdistrict")
        .agg(eligible_66=("บช_ผู้มีสิทธิ์","sum"), used_66=("บช_ผู้มาใช้สิทธิ์","sum"))
        .reset_index()
        .rename(columns={"subdistrict":"tambon_key"})
    )
    df_t66["turnout_rate_66"] = df_t66["used_66"] / df_t66["eligible_66"].where(df_t66["eligible_66"] > 0) * 100
    df_turnout = pd.merge(df_t69, df_t66, on="tambon_key")
    df_turnout["turnout_delta"] = df_turnout["turnout_rate_69"] - df_turnout["turnout_rate_66"]

    # compute party-level vote share delta
    df_party_growth = df_compare_kp.groupby("party_name").agg(
        total_votes_69=("votes_69","sum"), total_votes_66=("votes_66","sum")
    ).reset_index()
    g69 = df_party_growth["total_votes_69"].sum()
    g66 = df_party_growth["total_votes_66"].sum()
    df_party_growth["share_69"] = df_party_growth["total_votes_69"] / g69 * 100
    df_party_growth["share_66"] = df_party_growth["total_votes_66"] / g66 * 100
    df_party_growth["share_delta"] = df_party_growth["share_69"] - df_party_growth["share_66"]

    # precompute ballot checksum and spoil rate
    df_all_summary["check_sum"] = (
        df_all_summary[["ballots_valid","ballots_spoiled","ballots_no_vote"]]
        .sum(axis=1, min_count=1)
    )
    df_all_summary["spoiled_rate_percent"] = (
        df_all_summary["ballots_spoiled"]
        / df_all_summary["ballots_used"].where(df_all_summary["ballots_used"] > 0)
        * 100
    )

    # unit-level valid ballots for landslide calculation
    df_unit_valid = (
        df_all_summary[df_all_summary["type"]=="เขต"]
        [["amphoe","tambon","unit","ballots_valid"]].copy()
    )

    return {
        "df_final_report": df_final_report,
        "df_all_summary":  df_all_summary,
        "df_unit_valid":   df_unit_valid,
        "df_compare_kp":   df_compare_kp,
        "df_69_share":     df_69_share,
        "df_map":          df_map,
        "df_turnout":      df_turnout,
        "df_party_growth": df_party_growth,
        "winner_69":       winner_69,
        "winner_66":       winner_66,
        "matched":         matched,
        "loaded_amphoe":   loaded_amphoe,
    }


# Load
try:
    data = load_data()
except FileNotFoundError as e:
    st.error(f"ไม่พบไฟล์ข้อมูล: {e}\nกรุณาวางไฟล์ใน data/final/")
    st.stop()

df_final_report = data["df_final_report"]
df_all_summary  = data["df_all_summary"]
df_unit_valid   = data["df_unit_valid"]
df_compare_kp   = data["df_compare_kp"]
df_69_share     = data["df_69_share"]
df_map          = data["df_map"]
df_turnout      = data["df_turnout"]
df_party_growth = data["df_party_growth"]
winner_69       = data["winner_69"]
winner_66       = data["winner_66"]
matched         = data["matched"]
loaded_amphoe   = data["loaded_amphoe"]

# Sidebar
st.sidebar.title("Election Dashboard")
st.sidebar.caption("เขต 6 เชียงใหม่ — ปี 66 vs 69")
st.sidebar.divider()

# amphoe selector
all_amphoe = sorted(loaded_amphoe)
selected_amphoe = st.sidebar.multiselect(
    "อำเภอ",
    options=all_amphoe,
    placeholder="ทุกอำเภอ",
)
if not selected_amphoe:
    selected_amphoe = all_amphoe

# all tambons in selected amphoe (used as default)
all_tambons_in_amphoe = sorted(
    df_final_report[df_final_report["amphoe"].isin(selected_amphoe)]
    ["tambon"].str.replace("ตำบล","").str.strip().dropna().unique()
)
# selected_tambons is overridden per-page where needed

selected_tambons = list(all_tambons_in_amphoe)

# tambons matched with 66 data (for compare / map pages)
selected_tambons_matched = [t for t in selected_tambons if t in matched]

st.sidebar.divider()
page = st.sidebar.radio(
    "หน้า",
    ["ภาพรวม", "จัดอันดับ", "ความโปร่งใส", "Split-Ticket", "66 vs 69", "แผนที่", "Modeling"],
)


# Page: ภาพรวม
if page == "ภาพรวม":
    st.title("ภาพรวมการเลือกตั้ง — ปี 69")

    df_ov = df_final_report[df_final_report["amphoe"].isin(selected_amphoe)]
    total_votes_ss = df_ov[df_ov["type"]=="เขต"]["votes"].sum()
    total_votes_pl = df_ov[df_ov["type"]=="ปาร์ตี้ลิสต์"]["votes"].sum()
    total_tambons = df_ov["tambon"].nunique()
    spoiled_pl = df_all_summary[
        (df_all_summary["type"]=="ปาร์ตี้ลิสต์") &
        (df_all_summary["amphoe"].isin(selected_amphoe))
    ]["ballots_spoiled"].sum()
    spoiled_ss = df_all_summary[
        (df_all_summary["type"]=="เขต") &
        (df_all_summary["amphoe"].isin(selected_amphoe))
    ]["ballots_spoiled"].sum()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("คะแนนรวม (ส.ส. เขต)", f"{total_votes_ss:,}")
    c2.metric("คะแนนรวม (Party List)", f"{total_votes_pl:,}")
    c3.metric("จำนวนตำบล", f"{total_tambons:,}")
    c4.metric("บัตรเสีย (ปาร์ตี้ลิสต์)", f"{int(spoiled_pl or 0):,}")
    c5.metric("บัตรเสีย (ส.ส. เขต)", f"{int(spoiled_ss or 0):,}")

    st.divider()
    st.subheader("คะแนนรวมรายพรรค — ส.ส. เขต")
    top = (
        df_ov[df_ov["type"]=="เขต"]
        .groupby("party_name")["votes"].sum()
        .reset_index()
        .sort_values("votes", ascending=True)
    )
    fig = px.bar(
        top, x="votes", y="party_name", orientation="h",
        color="party_name",
        color_discrete_map={r["party_name"]: party_color(r["party_name"]) for _, r in top.iterrows()},
        labels={"votes":"คะแนน","party_name":"พรรค"},
        text="votes",
    )
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig.update_layout(showlegend=False, height=max(300, len(top)*28))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # filter by tambon
    st.subheader("กรองข้อมูลรายตำบล")
    tambon_sel = st.selectbox("เลือกตำบล", sorted(df_ov["tambon"].unique()))
    type_sel   = st.radio("ประเภท", ["เขต","ปาร์ตี้ลิสต์"], horizontal=True)
    df_filtered = df_ov[
        (df_ov["tambon"] == tambon_sel) &
        (df_ov["type"] == type_sel)
    ]
    st.dataframe(
        df_filtered[["unit","party_name","candidate_name","votes"]]
        .sort_values("votes", ascending=False),
        use_container_width=True,
    )

    st.divider()

    # landslide: units where a party won >= threshold % of valid ballots
    landslide_pct = st.slider(
        "Landslide threshold — % ของบัตรดีในหน่วย",
        min_value=0, max_value=100, value=80, step=1,
        format="%d%%",
    )

    df_land = pd.merge(
        df_ov[df_ov["type"]=="เขต"].copy(),
        df_unit_valid[df_unit_valid["amphoe"].isin(selected_amphoe)],
        on=["amphoe","tambon","unit"],
        how="left",
    )
    
    df_land["vote_pct"] = df_land["votes"] / df_land["ballots_valid"].where(df_land["ballots_valid"] > 0) * 100
    df_land = df_land[
        (df_land["vote_pct"] >= landslide_pct) & 
        (df_land["vote_pct"] <= 100)
    ].sort_values("vote_pct", ascending=False)

    st.subheader(f"Landslide — หน่วยที่พรรคได้คะแนน ≥ {landslide_pct}% ของบัตรดี  ({len(df_land)} หน่วย)")
    if df_land.empty:
        st.info("ไม่มีหน่วยที่เข้าเกณฑ์ Landslide")
    else:
        st.dataframe(
            df_land[["amphoe","tambon","unit","party_name","votes","ballots_valid","vote_pct"]]
            .rename(columns={"vote_pct":"% ของบัตรดี"}),
            use_container_width=True,
        )


# Page: จัดอันดับ
elif page == "จัดอันดับ":
    st.title("จัดอันดับ & ผู้ชนะ")

    df_rank = df_final_report[df_final_report["amphoe"].isin(selected_amphoe)]

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        # tambon filter (this page only)
        all_tambons_rank = sorted(
            df_rank["tambon"].str.replace("ตำบล","").str.strip().dropna().unique()
        )
        selected_tambons_rank = st.multiselect(
            "กรองตำบล",
            options=all_tambons_rank,
            default=[],
            placeholder="ทุกตำบล (ไม่เลือก = ทั้งหมด)",
        )
        if not selected_tambons_rank:
            selected_tambons_rank = all_tambons_rank

    with col_f2:
        # party filter (this page only)
        all_parties_rank = sorted(df_rank["party_name"].dropna().unique())
        selected_parties = st.multiselect(
            "กรองพรรค",
            options=all_parties_rank,
            default=[],
            placeholder="ทุกพรรค (ไม่เลือก = ทั้งหมด)",
        )
        if not selected_parties:
            selected_parties = all_parties_rank

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("คะแนนรวม ส.ส. เขต")
        top_parties = (
            df_rank[
                (df_rank["type"]=="เขต") &
                (df_rank["party_name"].isin(selected_parties))
            ]
            .groupby("party_name")["votes"].sum()
            .reset_index()
            .sort_values("votes", ascending=False)
        )
        fig1 = px.bar(
            top_parties, x="party_name", y="votes",
            color="party_name",
            color_discrete_map={r["party_name"]: party_color(r["party_name"]) for _, r in top_parties.iterrows()},
            text="votes",
            labels={"votes":"คะแนน","party_name":"พรรค"},
        )
        fig1.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig1.update_layout(showlegend=False, xaxis_tickangle=-30)
        st.plotly_chart(fig1, use_container_width=True)

    with col2:
        st.subheader("คะแนนรวม ปาร์ตี้ลิสต์ (Top 10)")
        top_pl = (
            df_rank[
                (df_rank["type"]=="ปาร์ตี้ลิสต์") &
                (df_rank["party_name"].isin(selected_parties))
            ]
            .groupby("party_name")["votes"].sum()
            .reset_index()
            .sort_values("votes", ascending=False)
            .head(10)
        )
        fig2 = px.bar(
            top_pl, x="party_name", y="votes",
            color="party_name",
            color_discrete_map={r["party_name"]: party_color(r["party_name"]) for _, r in top_pl.iterrows()},
            text="votes",
            labels={"votes":"คะแนน","party_name":"พรรค"},
        )
        fig2.update_traces(texttemplate="%{text:,}", textposition="outside")
        fig2.update_layout(showlegend=False, xaxis_tickangle=-30)
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()
    st.subheader("แชมป์ประจำตำบล — ส.ส. เขต (บน) vs ปาร์ตี้ลิสต์ (ล่าง)")

    # party-list winner per tambon
    tambon_champ_pl = (
        df_rank[
            (df_rank["type"] == "ปาร์ตี้ลิสต์") &
            (df_rank["tambon"].str.replace("ตำบล","").str.strip().isin(selected_tambons_rank)) &
            (df_rank["party_name"].isin(selected_parties))
        ]
        .groupby(["tambon","party_name"])["votes"].sum().reset_index()
    )
    best_pl = tambon_champ_pl.loc[
        tambon_champ_pl.groupby("tambon")["votes"].idxmax()
    ].copy()

    # constituency winner per tambon
    tambon_champ_ss = (
        df_rank[
            (df_rank["type"] == "เขต") &
            (df_rank["tambon"].str.replace("ตำบล","").str.strip().isin(selected_tambons_rank)) &
            (df_rank["party_name"].isin(selected_parties))
        ]
        .groupby(["tambon","party_name"])["votes"].sum().reset_index()
    )
    best_ss = tambon_champ_ss.loc[
        tambon_champ_ss.groupby("tambon")["votes"].idxmax()
    ].copy()

    # sort tambons by pl votes ascending (so highest appears at top in horizontal chart)
    tambon_order = best_pl.sort_values("votes", ascending=True)["tambon"].tolist()
    for t in best_ss["tambon"]:  # add ss-only tambons
        if t not in tambon_order:  # add ss-only tambons
            tambon_order.insert(0, t)

    ss_idx = best_ss.set_index("tambon").reindex(tambon_order)
    pl_idx = best_pl.set_index("tambon").reindex(tambon_order)

    fig3 = go.Figure()

    # top trace: constituency
    fig3.add_trace(go.Bar(
        name="ส.ส. เขต",
        y=tambon_order,
        x=ss_idx["votes"].fillna(0).tolist(),
        orientation="h",
        marker_color=[party_color(str(p)) for p in ss_idx["party_name"].tolist()],
        marker_line_color="white",
        marker_line_width=1.5,
        opacity=1.0,
        text=["ส.ส. เขต : " + str(p) for p in ss_idx["party_name"].tolist()],
        textposition="inside",
        insidetextanchor="middle",
    ))

    # bottom trace: party-list
    fig3.add_trace(go.Bar(
        name="ปาร์ตี้ลิสต์",
        y=tambon_order,
        x=pl_idx["votes"].fillna(0).tolist(),
        orientation="h",
        marker_color=[party_color(str(p)) for p in pl_idx["party_name"].tolist()],
        marker_line_color="white",
        marker_line_width=1.5,
        opacity=1.0,
        text=["ปาร์ตี้ลิสต์ : " + str(p) for p in pl_idx["party_name"].tolist()],
        textposition="inside",
        insidetextanchor="middle",
    ))

    fig3.update_layout(
        barmode="group",
        height=max(300, len(tambon_order) * 70),
        xaxis_title="คะแนน",
        yaxis_title="ตำบล",
        legend=dict(
            orientation="h", yanchor="bottom",
            y=1.02, xanchor="left", x=0,
        ),
    )
    st.plotly_chart(fig3, use_container_width=True)

    # side-by-side table: constituency vs party-list
    tbl = pd.merge(
        best_ss[["tambon","party_name","votes"]].rename(
            columns={"party_name":"พรรค (เขต)","votes":"คะแนน (เขต)"}),
        best_pl[["tambon","party_name","votes"]].rename(
            columns={"party_name":"พรรค (ปาร์ตี้ลิสต์)","votes":"คะแนน (ปาร์ตี้ลิสต์)"}),
        on="tambon", how="outer",
    )
    tbl["Split-Ticket"] = tbl["พรรค (เขต)"] != tbl["พรรค (ปาร์ตี้ลิสต์)"]
    st.dataframe(tbl.sort_values("คะแนน (เขต)", ascending=False), use_container_width=True)


# Page: ความโปร่งใส
elif page == "ความโปร่งใส":
    st.title("ตรวจสอบความโปร่งใส — Anomaly Detection")

    df_trans = df_all_summary[df_all_summary["amphoe"].isin(selected_amphoe)]

    df_ghost = df_trans[
        df_trans["ballots_used"].notna() &
        df_trans["check_sum"].notna() &
        (df_trans["ballots_used"] != df_trans["check_sum"])
    ]
    st.subheader(f"ยอดรวมบัตรที่ใช้ไม่เท่ากับที่ได้รับ — พบ {len(df_ghost)} หน่วย")
    if df_ghost.empty:
        st.success("ไม่พบหน่วยที่มีบัตรเขย่ง")
    else:
        df_ghost_show = df_ghost[["amphoe","tambon","unit","type","ballots_used","check_sum"]].copy()
        df_ghost_show["ส่วนต่าง"] = df_ghost_show["ballots_used"] - df_ghost_show["check_sum"]
        st.dataframe(df_ghost_show, use_container_width=True)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 บัตรเสียสูงสุด")
        st.dataframe(
            df_trans.nlargest(10, "ballots_spoiled")
            [["amphoe","tambon","unit","type","ballots_spoiled","ballots_used"]],
            use_container_width=True,
        )
    with col2:
        st.subheader("% บัตรเสียรายตำบล")
        spoiled_by_tambon = (
            df_trans[df_trans["type"]=="ปาร์ตี้ลิสต์"]
            .groupby("tambon")
            .agg(spoiled=("ballots_spoiled","sum"), used=("ballots_used","sum"))
            .reset_index()
        )
        spoiled_by_tambon["spoiled_pct"] = spoiled_by_tambon["spoiled"] / spoiled_by_tambon["used"].where(spoiled_by_tambon["used"] > 0) * 100
        sorted_spoiled = spoiled_by_tambon[spoiled_by_tambon["spoiled_pct"] > 0].sort_values("spoiled_pct", ascending=False)
        
        if sorted_spoiled.empty:
            st.info("ไม่มีข้อมูลบัตรเสีย (หรือเป็น 0% ทั้งหมด)")
        else:
            fig = px.bar(
                sorted_spoiled,
                x="tambon", y="spoiled_pct",
                color="spoiled_pct", color_continuous_scale="Reds",
                text=sorted_spoiled["spoiled_pct"].round(2).astype(str) + "%",
                labels={"spoiled_pct":"% บัตรเสีย","tambon":"ตำบล"},
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(coloraxis_showscale=False, xaxis_tickangle=-30)
            st.plotly_chart(fig, use_container_width=True)

    st.divider()
    threshold_pct = st.slider("แสดงหน่วยที่บัตรเสียเกิน (%)", 0, 50, 10)
    high_spoiled = df_trans[df_trans["spoiled_rate_percent"] > threshold_pct][
        ["amphoe","tambon","unit","type","ballots_spoiled","ballots_used","spoiled_rate_percent"]
    ].sort_values("spoiled_rate_percent", ascending=False)
    st.subheader(f"หน่วยที่บัตรเสียเกิน {threshold_pct}% — พบ {len(high_spoiled)} หน่วย")
    st.dataframe(high_spoiled, use_container_width=True)


# Page: Split-Ticket
elif page == "Split-Ticket":
    st.title("Split-Ticket Voting — เขต vs ปาร์ตี้ลิสต์")

    df_st = df_final_report[
        (df_final_report["amphoe"].isin(selected_amphoe)) &
        (df_final_report["tambon"] != "ไม่ระบุ")
    ]
    
    df_pivot = df_st.pivot_table(
        index=["tambon","unit","party_name"],
        columns="type", values="votes", aggfunc="sum",
    ).reset_index().fillna(0)
    df_pivot.columns.name = None
    if "เขต" not in df_pivot.columns:        df_pivot["เขต"] = 0
    if "ปาร์ตี้ลิสต์" not in df_pivot.columns: df_pivot["ปาร์ตี้ลิสต์"] = 0
    df_pivot["split_vote_diff"] = df_pivot["ปาร์ตี้ลิสต์"] - df_pivot["เขต"]

    all_parties_st = sorted(df_pivot["party_name"].dropna().unique())
    selected_parties_st = st.multiselect(
        "กรองพรรค",
        options=all_parties_st, default=[],
        placeholder="ทุกพรรค (ไม่เลือก = ทั้งหมด)",
    )
    if not selected_parties_st:
        selected_parties_st = all_parties_st

    df_pv = df_pivot[df_pivot["party_name"].isin(selected_parties_st)]

    st.subheader("Top 15 หน่วยที่ split-ticket สูงสุด (กา party list มากกว่าเขต)")
    top15 = df_pv[df_pv["split_vote_diff"] > 0].sort_values("split_vote_diff", ascending=False).head(15)
    fig = px.bar(
        top15, x="split_vote_diff",
        y=top15["tambon"] + " | " + top15["unit"] + " | " + top15["party_name"],
        orientation="h",
        color="party_name",
        color_discrete_map={p: party_color(p) for p in top15["party_name"].unique()},
        labels={"x":"ส่วนต่าง (ปาร์ตี้ลิสต์ − เขต)","y":""},
        text="split_vote_diff",
    )
    fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig.update_layout(showlegend=False, height=450)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Scatter: คะแนนเขต vs ปาร์ตี้ลิสต์ รายพรรค (ตัด Outlier ที่ P95)")
    df_scatter = df_pv[(df_pv["เขต"] > 0) & (df_pv["ปาร์ตี้ลิสต์"] > 0)].copy()

    if not df_scatter.empty:
        p95_khet = df_scatter["เขต"].quantile(0.95)
        p95_plist = df_scatter["ปาร์ตี้ลิสต์"].quantile(0.95)
        df_scatter = df_scatter[
            (df_scatter["เขต"] <= p95_khet) & 
            (df_scatter["ปาร์ตี้ลิสต์"] <= p95_plist)
        ]
    if df_scatter.empty:
        st.info("ไม่มีข้อมูลสำหรับ Scatter")
    else:
        fig2 = px.scatter(
            df_scatter,
            x="เขต", y="ปาร์ตี้ลิสต์",
            color="party_name",
            color_discrete_map={p: party_color(p) for p in df_scatter["party_name"].unique()},
            hover_data=["tambon","unit"],
            labels={"เขต":"คะแนน ส.ส. เขต","ปาร์ตี้ลิสต์":"คะแนนปาร์ตี้ลิสต์"},
        )
        max_val = max(df_scatter["เขต"].max(), df_scatter["ปาร์ตี้ลิสต์"].max())
        fig2.add_shape(type="line", x0=0, y0=0, x1=max_val, y1=max_val,
                       line=dict(color="gray", dash="dash"))
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("ตารางทั้งหมด")
    st.dataframe(df_pv.sort_values("split_vote_diff", ascending=False), use_container_width=True)


# Page: 66 vs 69
elif page == "66 vs 69":
    st.title("เปรียบเทียบ 66 vs 69")
    st.info(
        "พรรคประชาชน + พรรคก้าวไกล ถูกรวมเป็น **ประชาชน/ก้าวไกล** เพื่อการเปรียบเทียบ"
    )

    tab1, tab2, tab3, tab4 = st.tabs(["Party Growth","Vote Share Swing","Voter Turnout","Swing Voter"])

    with tab1:
        st.subheader("Party Growth / Decay — vote share delta")
        df_pg = df_party_growth.sort_values("share_delta")
        df_pg["color"] = df_pg["share_delta"].apply(lambda x: "#2E7D32" if x >= 0 else "#C62828")
        fig = px.bar(
            df_pg, x="share_delta", y="party_name", orientation="h",
            color="color", color_discrete_map="identity",
            text=df_pg["share_delta"].round(2).astype(str) + "%",
            labels={"share_delta":"Vote Share Δ (%)","party_name":"พรรค"},
        )
        fig.add_vline(x=0, line_color="black", line_width=1)
        fig.update_traces(textposition="outside")
        fig.update_layout(showlegend=False, height=max(300, len(df_pg)*32))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            df_pg[["party_name","share_66","share_69","share_delta","total_votes_66","total_votes_69"]]
            .sort_values("share_delta", ascending=False)
            .rename(columns={"share_66":"share% 66","share_69":"share% 69","share_delta":"Δ%"}),
            use_container_width=True,
        )

    with tab2:
        st.subheader("Vote Share Swing รายตำบล")
        df_swing = df_69_share[df_69_share["tambon_key"].isin(selected_tambons_matched)]
        if df_swing.empty:
            st.info("ไม่มีข้อมูลตำบลที่เลือก")
        else:
            party_pick = st.selectbox("เลือกพรรค", sorted(df_swing["party_name"].unique()))
            df_swing_p = df_swing[df_swing["party_name"]==party_pick].sort_values("share_swing")
            df_swing_p["color"] = df_swing_p["share_swing"].apply(lambda x: "#2E7D32" if x >= 0 else "#C62828")
            fig = px.bar(
                df_swing_p, x="share_swing", y="tambon_key", orientation="h",
                color="color", color_discrete_map="identity",
                text=df_swing_p["share_swing"].round(2).astype(str) + "%",
                labels={"share_swing":"Swing (%)","tambon_key":"ตำบล"},
                title=f"Swing พรรค{party_pick} — ปี 66→69",
            )
            fig.add_vline(x=0, line_color="black", line_width=1)
            fig.update_traces(textposition="outside")
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    with tab3:
        st.subheader("Voter Turnout 66 vs 69")
        df_t = df_turnout[df_turnout["tambon_key"].isin(selected_tambons_matched)]
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Turnout 66", x=df_t["tambon_key"], y=df_t["turnout_rate_66"], marker_color="#90CAF9"))
        fig.add_trace(go.Bar(name="Turnout 69", x=df_t["tambon_key"], y=df_t["turnout_rate_69"], marker_color="#1565C0"))
        fig.update_layout(barmode="group", yaxis_title="Turnout (%)", xaxis_tickangle=-30)
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(
            df_t[["tambon_key","turnout_rate_66","turnout_rate_69","turnout_delta"]]
            .sort_values("turnout_delta", ascending=False),
            use_container_width=True,
        )

    with tab4:
        st.subheader("Swing Voter — ตำบลที่แชมป์เปลี่ยน")
        w_cmp = winner_69.merge(winner_66[["tambon_key","winner_66"]], on="tambon_key")
        w_cmp["flipped"] = w_cmp["winner_69"] != w_cmp["winner_66"]
        flipped = w_cmp[w_cmp["flipped"] & w_cmp["tambon_key"].isin(selected_tambons_matched)]
        held    = w_cmp[~w_cmp["flipped"] & w_cmp["tambon_key"].isin(selected_tambons_matched)]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("ตำบลที่เปลี่ยนแชมป์", len(flipped))
            if flipped.empty:
                st.info("ไม่มีตำบลที่เปลี่ยนแชมป์")
            else:
                st.dataframe(flipped[["tambon_key","winner_66","winner_69"]], use_container_width=True)
        with col2:
            st.metric("ตำบลที่ยังครองได้", len(held))
            st.dataframe(held[["tambon_key","winner_69"]], use_container_width=True)


# Page: แผนที่
elif page == "แผนที่":
    st.title("แผนที่ผู้ชนะรายตำบล")

    df_m = df_map[df_map["tambon_key"].isin(selected_tambons_matched)]

    col1, col2, col3 = st.columns(3)
    col1.metric("ตำบลทั้งหมดบนแผนที่", len(df_m))
    col2.metric("ตำบลที่แชมป์เปลี่ยน",  int(df_m["flipped"].sum()))
    col3.metric("ตำบลที่แชมป์ยังครอง",  int((~df_m["flipped"]).sum()))

    center_lat = df_m["lat_changable"].mean() if not df_m.empty else 19.37
    center_lng = df_m["lng_changable"].mean() if not df_m.empty else 98.97
    m = folium.Map(location=[center_lat, center_lng], zoom_start=10, tiles="CartoDB positron")

    for _, row in df_m.iterrows():
        color     = PARTY_COLORS.get(row["winner_69"], DEFAULT_COLOR)
        flip_icon = "[+] " if row["flipped"] else ""
        folium.CircleMarker(
            location=[row["lat_changable"], row["lng_changable"]],
            radius=13, color="white", weight=2,
            fill=True, fill_color=color, fill_opacity=0.85,
            popup=folium.Popup(
                f"{flip_icon}<b>{row['subdistrict']}</b><br>"
                f"66: {row['winner_66']}<br>"
                f"69: {row['winner_69']}<br>"
                f"คะแนน 69: {int(row['votes_69']):,}",
                max_width=200,
            ),
            tooltip=f"{row['subdistrict']} → {row['winner_69']}",
        ).add_to(m)

    st_folium(m, width=None, height=500)
    st.divider()

    st.subheader("Legend")
    leg_cols = st.columns(len(PARTY_COLORS)+1)
    for i, (pname, pcolor) in enumerate(PARTY_COLORS.items()):
        leg_cols[i].markdown(
            f"<span style='background:{pcolor};padding:3px 10px;border-radius:4px;color:white'>{pname}</span>",
            unsafe_allow_html=True,
        )
    leg_cols[-1].markdown(
        f"<span style='background:{DEFAULT_COLOR};padding:3px 10px;border-radius:4px;color:white'>อื่นๆ</span>",
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("ข้อมูลรายตำบล")
    st.dataframe(
        df_m[["subdistrict","winner_66","winner_69","votes_69","flipped"]]
        .rename(columns={"subdistrict":"ตำบล","winner_66":"ชนะ 66","winner_69":"ชนะ 69",
                         "votes_69":"คะแนน 69","flipped":"เปลี่ยนแชมป์"})
        .sort_values("คะแนน 69", ascending=False),
        use_container_width=True,
    )

# Page: Modeling
elif page == "Modeling":
    st.title("Modeling Pipeline")
    st.caption("4 การวิเคราะห์เชิงสถิติ: Concentration · Clustering · Anomaly · Split-Ticket Regression")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Concentration", "Clustering", "Anomaly", "Regression"]
    )

    # Tab 1: Concentration
    with tab1:
        st.subheader("Vote Concentration — ENP / HHI / Top-share / Margin")
        st.markdown(
            "**ENP (Effective Number of Parties)** = 1 / Σsᵢ²  \n"
            "ค่าสูง = คะแนนกระจายหลายพรรค, ค่าต่ำ = กระจุกอยู่ไม่กี่พรรค  \n"
            "**HHI** = Σsᵢ² (ยิ่งสูง ยิ่ง monopolize)"
        )

        with st.spinner("คำนวณ Concentration metrics..."):
            df_conc = compute_concentration(df_final_report)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Median ENP (ปาร์ตี้ลิสต์)",   f"{df_conc['ENP_plist'].median():.2f}")
        col2.metric("Median ENP (เขต)",              f"{df_conc['ENP_khet'].median():.2f}")
        col3.metric("Median Top-share (ปาร์ตี้ลิสต์)", f"{df_conc['top_share_plist'].median():.1%}")
        col4.metric("Median Margin (ปาร์ตี้ลิสต์)",  f"{df_conc['margin_plist'].median():.1%}")

        fig_enp = px.scatter(
            df_conc.dropna(subset=["ENP_plist", "ENP_khet"]),
            x="ENP_plist", y="ENP_khet",
            hover_data=["tambon", "unit"],
            title="ENP: ปาร์ตี้ลิสต์ vs เขต (รายหน่วย)",
            labels={"ENP_plist": "ENP ปาร์ตี้ลิสต์", "ENP_khet": "ENP เขต"},
            opacity=0.65,
        )
        max_enp = df_conc["ENP_plist"].max()
        fig_enp.add_shape(
            type="line", x0=0, x1=max_enp, y0=0, y1=max_enp,
            line=dict(dash="dash", color="gray", width=1),
        )
        st.plotly_chart(fig_enp, use_container_width=True)

        tambon_conc = (
            df_conc.groupby("tambon")[["ENP_plist", "ENP_khet", "top_share_plist", "margin_plist"]]
            .mean().round(3).sort_values("ENP_plist").reset_index()
        )
        st.subheader("ค่าเฉลี่ยรายตำบล")
        st.dataframe(
            tambon_conc.rename(columns={
                "tambon":          "ตำบล",
                "ENP_plist":       "ENP (ปาร์ตี้ลิสต์)",
                "ENP_khet":        "ENP (เขต)",
                "top_share_plist": "Top-share (ปาร์ตี้ลิสต์)",
                "margin_plist":    "Margin (ปาร์ตี้ลิสต์)",
            }),
            use_container_width=True,
        )

    # Tab 2: Clustering
    with tab2:
        st.subheader("Political Clustering of Polling Units")

        with st.spinner("รัน PCA + KMeans..."):
            clust = compute_clustering(df_final_report)

        st.markdown(
            f"PCA + KMeans บน vote share ของ **10 พรรคคะแนนนำ** (ปาร์ตี้ลิสต์)  \n"
            f"**K ที่เลือก = {clust['best_k']}** (silhouette score สูงสุด)  \n"
            f"PC1 = {clust['pca_var'][0]:.1%}, PC2 = {clust['pca_var'][1]:.1%}, "
            f"รวม = {clust['pca_var'][:2].sum():.1%}"
        )

        sil_df = pd.DataFrame(clust["silhouette_scores"], columns=["K", "Silhouette"])
        fig_sil = px.bar(
            sil_df, x="K", y="Silhouette",
            title="Silhouette Score by K",
            color_discrete_sequence=["#636EFA"],
        )
        st.plotly_chart(fig_sil, use_container_width=True)

        comp     = clust["comp"]
        clusters = clust["clusters"]
        pca_df   = pd.DataFrame({
            "PC1":     comp[:, 0],
            "PC2":     comp[:, 1],
            "Cluster": clusters.astype(str),
            "ตำบล":   clust["shares"].index.get_level_values("tambon"),
            "หน่วย":  clust["shares"].index.get_level_values("unit"),
        })
        fig_pca = px.scatter(
            pca_df, x="PC1", y="PC2", color="Cluster",
            hover_data=["ตำบล", "หน่วย"],
            title="Polling-unit clusters — PC1 vs PC2",
            labels={
                "PC1": f"PC1 ({clust['pca_var'][0]:.1%})",
                "PC2": f"PC2 ({clust['pca_var'][1]:.1%})",
            },
        )
        st.plotly_chart(fig_pca, use_container_width=True)

        profile_long = (
            clust["profile"].reset_index()
            .melt(id_vars="cluster", var_name="พรรค", value_name="Vote Share")
        )
        profile_long["Cluster"] = profile_long["cluster"].astype(str)
        fig_prof = px.bar(
            profile_long, x="พรรค", y="Vote Share", color="Cluster",
            barmode="group",
            title="Cluster Profiles — Mean Vote Share (ปาร์ตี้ลิสต์)",
        )
        fig_prof.update_layout(xaxis_tickangle=-40)
        st.plotly_chart(fig_prof, use_container_width=True)

        with st.expander("PC Loadings (ดูว่าพรรคไหนขับเคลื่อน PC1/PC2)"):
            st.dataframe(
                clust["loadings"].reset_index()
                .rename(columns={"party_name": "พรรค"})
                .sort_values("PC1").round(3),
                use_container_width=True,
            )

        st.subheader("Cluster Geography")
        df_uc = pd.DataFrame({
            "tambon":  clust["shares"].index.get_level_values("tambon"),
            "cluster": clusters,
        })
        df_uc["tambon_clean"] = df_uc["tambon"].str.replace("ตำบล", "", regex=False).str.strip()

        cluster_cols_k = sorted(df_uc["cluster"].unique())
        cmix = (df_uc.groupby(["tambon_clean", "cluster"])
                .size().unstack(fill_value=0))
        cmix["dominant"] = cmix[cluster_cols_k].idxmax(axis=1)
        cmix = cmix.reset_index()

        df_geo2 = (
            df_map[["subdistrict", "lat_changable", "lng_changable"]]
            .rename(columns={"subdistrict": "tambon_clean"})
        )
        df_cmap = cmix.merge(df_geo2, on="tambon_clean", how="left").dropna(subset=["lat_changable"])

        CLUSTER_COLORS = ["orange", "steelblue", "crimson", "seagreen", "purple"]
        center_lat = df_cmap["lat_changable"].mean() if not df_cmap.empty else 19.37
        center_lng = df_cmap["lng_changable"].mean() if not df_cmap.empty else 98.97
        m_clust = folium.Map(location=[center_lat, center_lng],
                             zoom_start=10, tiles="CartoDB positron")
        for _, r in df_cmap.iterrows():
            dom   = int(r["dominant"])
            color = CLUSTER_COLORS[dom % len(CLUSTER_COLORS)]
            folium.CircleMarker(
                location=[r["lat_changable"], r["lng_changable"]],
                radius=11,
                color="white", weight=1,
                fill=True, fill_color=color, fill_opacity=0.82,
                tooltip=f"{r['tambon_clean']} → Cluster {dom}",
            ).add_to(m_clust)
        st_folium(m_clust, width=None, height=460)

    # Tab 3: Anomaly
    with tab3:
        st.subheader("Anomaly Detection — Isolation Forest")
        st.markdown(
            "Feature vector ต่อหน่วย: `spoil_rate`, `no_vote_rate`, `ENP_plist`, `ENP_khet`, "
            "`top_share_plist`, `margin_plist`  \n"
            "Contamination = 8%"
        )

        with st.spinner("รัน Isolation Forest..."):
            if "df_conc" not in dir():
                df_conc = compute_concentration(df_final_report)
            df_feat, feat_cols = compute_anomaly(df_all_summary, df_conc)

        n_anom = int(df_feat["is_anomaly"].sum())
        col1, col2, col3 = st.columns(3)
        col1.metric("หน่วยทั้งหมด",  len(df_feat))
        col2.metric("หน่วย Anomaly", n_anom)
        col3.metric("สัดส่วน",       f"{n_anom / len(df_feat):.1%}")

        show_cols = ["tambon", "unit", "ballots_used",
                     "spoil_rate", "no_vote_rate",
                     "ENP_plist", "top_share_plist", "anomaly_score"]
        top_anom = df_feat.sort_values("anomaly_score", ascending=False).head(10)[show_cols].copy()
        for c in ["spoil_rate", "no_vote_rate", "top_share_plist"]:
            top_anom[c] = (top_anom[c] * 100).round(2)
        top_anom["anomaly_score"] = top_anom["anomaly_score"].round(3)

        st.subheader("Top 10 Anomalous Units")
        st.dataframe(
            top_anom.rename(columns={
                "tambon":          "ตำบล",
                "unit":            "หน่วย",
                "ballots_used":    "บัตรที่ใช้",
                "spoil_rate":      "บัตรเสีย %",
                "no_vote_rate":    "โหวตโน %",
                "ENP_plist":       "ENP",
                "top_share_plist": "Top-share %",
                "anomaly_score":   "Anomaly Score",
            }),
            use_container_width=True,
        )

        fig_anom = px.scatter(
            df_feat,
            x="spoil_rate", y="anomaly_score",
            color=df_feat["is_anomaly"].map({True: "Anomaly", False: "ปกติ"}),
            hover_data=["tambon", "unit", "no_vote_rate", "ENP_plist"],
            title="Anomaly Score vs อัตราบัตรเสีย",
            labels={"spoil_rate": "Spoil Rate", "anomaly_score": "Anomaly Score"},
            color_discrete_map={"Anomaly": "#EF553B", "ปกติ": "#636EFA"},
            opacity=0.72,
        )
        st.plotly_chart(fig_anom, use_container_width=True)

        fig_enp_anom = px.scatter(
            df_feat,
            x="ENP_plist", y="anomaly_score",
            color=df_feat["is_anomaly"].map({True: "Anomaly", False: "ปกติ"}),
            hover_data=["tambon", "unit", "spoil_rate"],
            title="Anomaly Score vs ENP ปาร์ตี้ลิสต์",
            labels={"ENP_plist": "ENP (ปาร์ตี้ลิสต์)", "anomaly_score": "Anomaly Score"},
            color_discrete_map={"Anomaly": "#EF553B", "ปกติ": "#636EFA"},
            opacity=0.72,
        )
        st.plotly_chart(fig_enp_anom, use_container_width=True)

    # Tab 4: Regression
    with tab4:
        st.subheader("Split-Ticket Regression")
        st.markdown(
            "วิเคราะห์ว่า feature ใดอธิบาย **split-ticket gap** "
            "(share ปาร์ตี้ลิสต์ − share เขต) ของพรรคคะแนนนำ  \n"
            "Model: OLS (interpretability) + XGBoost (non-linear) + SHAP (feature importance)"
        )

        try:
            with st.spinner("รัน OLS + XGBoost + SHAP..."):
                _df_conc_r = compute_concentration(df_final_report)
                _df_feat_r, _ = compute_anomaly(df_all_summary, _df_conc_r)
                reg = compute_regression(df_final_report, _df_feat_r)
        except ImportError as e:
            st.error(f"ต้องติดตั้ง library เพิ่มก่อน: {e}")
            st.info("รัน: `pip install statsmodels xgboost shap`")
            st.stop()

        st.info(f"**Target party:** {reg['target_party']}  |  N = {reg['sample_size']} units")

        col1, col2 = st.columns(2)
        col1.metric("OLS R²",      f"{reg['ols_r2']:.3f}")
        col2.metric("OLS Adj R²",  f"{reg['ols_r2_adj']:.3f}")

        st.subheader("OLS Coefficients")
        ols_t = reg["ols_table"].copy().round(4)
        ols_t["p<0.05"] = ols_t["p_value"] < 0.05
        st.dataframe(
            ols_t.rename(columns={
                "variable": "Variable",
                "coef":     "Coef",
                "std_err":  "Std Err",
                "t":        "t-stat",
                "p_value":  "p-value",
            }),
            use_container_width=True,
        )

        st.subheader("SHAP Feature Importance (XGBoost)")
        fig_shap = px.bar(
            reg["shap_df"],
            x="mean_abs_shap", y="feature",
            orientation="h",
            title=f"Mean |SHAP value| — split-ticket gap สำหรับพรรค{reg['target_party']}",
            labels={"mean_abs_shap": "Mean |SHAP|", "feature": "Feature"},
            color="mean_abs_shap",
            color_continuous_scale="oranges",
        )
        fig_shap.update_layout(coloraxis_showscale=False)
        st.plotly_chart(fig_shap, use_container_width=True)