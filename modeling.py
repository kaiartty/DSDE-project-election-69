"""
modeling.py - Section 4: Modeling Pipeline

Functions:
    compute_concentration  - ENP / HHI / top-share / margin
    compute_clustering     - PCA + KMeans (party-list top-10)
    compute_anomaly        - Isolation Forest
    compute_regression     - OLS + XGBoost + SHAP
"""

import numpy as np
import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# 4.1  Vote Concentration
# ---------------------------------------------------------------------------

@st.cache_data
def compute_concentration(df_final_report: pd.DataFrame) -> pd.DataFrame:
    """
    Compute ENP, HHI, top-share, margin per polling unit
    for both party-list (_plist) and constituency (_khet).

    Returns
    -------
    df_conc : DataFrame  columns = [tambon, unit,
                                     ENP_plist, HHI_plist, top_share_plist, margin_plist,
                                     ENP_khet,  HHI_khet,  top_share_khet,  margin_khet]
    """
    def _metrics(group: pd.DataFrame) -> pd.Series:
        v = group["votes"].values.astype(float)
        total = v.sum()
        if total == 0:
            return pd.Series({"ENP": np.nan, "HHI": np.nan,
                               "top_share": np.nan, "margin": np.nan})
        s        = v[v > 0] / total
        s_sorted = np.sort(s)[::-1]
        return pd.Series({
            "ENP":       1.0 / (s ** 2).sum(),
            "HHI":       float((s ** 2).sum()),
            "top_share": float(s_sorted[0]),
            "margin":    float(s_sorted[0] - s_sorted[1]) if len(s_sorted) >= 2 else float(s_sorted[0]),
        })

    conc_plist = (
        df_final_report[df_final_report["type"] == "ปาร์ตี้ลิสต์"]
        .groupby(["tambon", "unit"])
        .apply(_metrics, include_groups=False)
        .add_suffix("_plist")
        .reset_index()
    )
    conc_khet = (
        df_final_report[df_final_report["type"] == "เขต"]
        .groupby(["tambon", "unit"])
        .apply(_metrics, include_groups=False)
        .add_suffix("_khet")
        .reset_index()
    )
    return conc_plist.merge(conc_khet, on=["tambon", "unit"], how="outer")


# ---------------------------------------------------------------------------
# 4.2  Political Clustering
# ---------------------------------------------------------------------------

@st.cache_data
def compute_clustering(df_final_report: pd.DataFrame) -> dict:
    """
    PCA (2D) + KMeans on vote-share of top-10 parties (party-list).
    K selected by highest silhouette score (K=2..5).

    Returns dict:
        shares, comp, clusters, pca_var,
        profile, best_k, loadings, silhouette_scores
    """
    from sklearn.decomposition import PCA
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score

    top10 = (
        df_final_report[df_final_report["type"] == "ปาร์ตี้ลิสต์"]
        .groupby("party_name")["votes"].sum()
        .nlargest(10).index
    )
    pivot = (
        df_final_report[
            (df_final_report["type"] == "ปาร์ตี้ลิสต์") &
            (df_final_report["party_name"].isin(top10))
        ]
        .pivot_table(index=["tambon", "unit"], columns="party_name",
                     values="votes", aggfunc="sum")
        .fillna(0)
    )
    shares = pivot.div(pivot.sum(axis=1), axis=0).dropna()

    X    = StandardScaler().fit_transform(shares.values)
    pca  = PCA(n_components=2)
    comp = pca.fit_transform(X)

    scores = [
        (k, silhouette_score(
            comp,
            KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(comp),
        ))
        for k in range(2, 6)
    ]
    best_k   = max(scores, key=lambda x: x[1])[0]
    clusters = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(comp)
    profile  = shares.assign(cluster=clusters).groupby("cluster").mean().round(3)
    loadings = pd.DataFrame(
        pca.components_.T, index=shares.columns, columns=["PC1", "PC2"]
    )

    return {
        "shares":            shares,
        "comp":              comp,
        "clusters":          clusters,
        "pca_var":           pca.explained_variance_ratio_,
        "profile":           profile,
        "best_k":            best_k,
        "loadings":          loadings,
        "silhouette_scores": scores,
    }


# ---------------------------------------------------------------------------
# 4.4  Anomaly Detection
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "spoil_rate", "no_vote_rate",
    "ENP_plist", "ENP_khet",
    "top_share_plist", "margin_plist",
]

@st.cache_data
def compute_anomaly(
    _df_all_summary: pd.DataFrame,
    _df_conc: pd.DataFrame,
    contamination: float = 0.08,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Isolation Forest on per-unit feature vector.
    Underscore prefix prevents st.cache_data from hashing the DataFrames.

    Returns
    -------
    (df_features, feature_cols)
    """
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    sum_p = _df_all_summary[_df_all_summary["type"] == "ปาร์ตี้ลิสต์"].copy()
    for c in ["ballots_used", "ballots_valid", "ballots_spoiled", "ballots_no_vote"]:
        sum_p[c] = pd.to_numeric(sum_p[c], errors="coerce")

    sum_p["spoil_rate"]   = sum_p["ballots_spoiled"] / sum_p["ballots_used"]
    sum_p["no_vote_rate"] = sum_p["ballots_no_vote"]  / sum_p["ballots_used"]
    sum_p["valid_rate"]   = sum_p["ballots_valid"]    / sum_p["ballots_used"]

    df_feat = (
        sum_p[["tambon", "unit", "ballots_used",
               "spoil_rate", "no_vote_rate", "valid_rate"]]
        .merge(_df_conc, on=["tambon", "unit"], how="left")
        .dropna(subset=FEATURE_COLS)
        .reset_index(drop=True)
    )

    X = StandardScaler().fit_transform(df_feat[FEATURE_COLS])
    iso = IsolationForest(contamination=contamination, random_state=42).fit(X)

    df_feat["anomaly_score"] = -iso.decision_function(X)
    df_feat["is_anomaly"]    = iso.predict(X) == -1

    return df_feat, FEATURE_COLS


# ---------------------------------------------------------------------------
# 4.5  Split-Ticket Regression
# ---------------------------------------------------------------------------

@st.cache_data
def compute_regression(
    _df_final_report: pd.DataFrame,
    _df_features: pd.DataFrame,
) -> dict:
    """
    OLS + XGBoost + SHAP for split-ticket gap of the leading party.

    Returns dict:
        target_party, sample_size,
        ols_table, ols_r2, ols_r2_adj,
        shap_df
    """
    import statsmodels.api as sm
    import xgboost as xgb
    import shap

    # Wide pivot: each row = (tambon, unit, party_name) with vote shares for both systems
    df_pv = (
        _df_final_report
        .pivot_table(
            index=["tambon", "unit", "party_name"],
            columns="type", values="votes", aggfunc="sum",
        )
        .fillna(0)
        .reset_index()
    )
    df_pv.columns.name = None

    unit_p = df_pv.groupby(["tambon", "unit"])["ปาร์ตี้ลิสต์"].transform("sum")
    unit_k = df_pv.groupby(["tambon", "unit"])["เขต"].transform("sum")
    df_pv["share_plist"]   = df_pv["ปาร์ตี้ลิสต์"] / unit_p
    df_pv["share_khet"]    = df_pv["เขต"]           / unit_k
    df_pv["split_gap_pct"] = df_pv["share_plist"] - df_pv["share_khet"]

    target_party = df_pv.groupby("party_name")["ปาร์ตี้ลิสต์"].sum().idxmax()

    df_t = (
        df_pv[df_pv["party_name"] == target_party]
        .merge(
            _df_features[["tambon", "unit"] + FEATURE_COLS],
            on=["tambon", "unit"], how="inner",
        )
        .dropna(subset=["split_gap_pct"])
        .reset_index(drop=True)
    )

    X   = df_t[FEATURE_COLS].astype(float)
    y   = df_t["split_gap_pct"].astype(float)
    ols = sm.OLS(y, sm.add_constant(X)).fit()

    model = xgb.XGBRegressor(
        n_estimators=300, max_depth=3, learning_rate=0.05, random_state=42
    )
    model.fit(X, y)

    shap_vals = shap.TreeExplainer(model).shap_values(X)
    shap_df   = pd.DataFrame({
        "feature":       FEATURE_COLS,
        "mean_abs_shap": np.abs(shap_vals).mean(axis=0),
    }).sort_values("mean_abs_shap", ascending=True)

    ols_table = pd.DataFrame({
        "coef":    ols.params,
        "std_err": ols.bse,
        "t":       ols.tvalues,
        "p_value": ols.pvalues,
    }).reset_index().rename(columns={"index": "variable"})

    return {
        "target_party": target_party,
        "sample_size":  len(df_t),
        "ols_table":    ols_table,
        "ols_r2":       ols.rsquared,
        "ols_r2_adj":   ols.rsquared_adj,
        "shap_df":      shap_df,
    }