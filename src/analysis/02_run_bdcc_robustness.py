#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BDCC robustness and validation suite for the publication-safe restaurant POS data.

Designed for:
  data/public/baskets_public_safe.csv
  data/public/items_public_safe.csv
  results/public/association_rules_validated_cds_public.csv (optional, for CDS audit)

Main outputs:
  00_data_audit.csv
  01_discovery_validation_summary.csv
  02_rule_validation_detail.csv
  03_threshold_sensitivity.csv
  04_nb_model_comparison.csv
  05_nb2_clustered_coefficients.csv
  06_gamma_sensitivity_summary.csv
  07_gamma_sensitivity_coefficients.csv
  08_cds_reparameterization.csv
  09_cds_weight_sensitivity.csv
  10_scalability_benchmark.csv
  10_scalability_benchmark_extended.csv
  11_reconstructed_rules_cds.csv
  bdcc_robustness_summary.md

The script does not modify source data.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import math
import time
import tracemalloc
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, spearmanr
from statsmodels.stats.multitest import multipletests
import statsmodels.api as sm
import statsmodels.formula.api as smf


WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SERVICE_INTERVALS = [
    "Early service (00-11)",
    "Lunch (12-15)",
    "Afternoon (16-18)",
    "Dinner (19-21)",
    "Late evening (22-23)",
]
BASE_MIN_SUPPORT = 100 / 31157  # reproduces the manuscript's 100-basket threshold on the full sample


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run BDCC robustness analyses on publication-safe POS data.")
    p.add_argument("--baskets", type=Path, default=Path("data/public/baskets_public_safe.csv"))
    p.add_argument("--items", type=Path, default=Path("data/public/items_public_safe.csv"))
    p.add_argument(
        "--rules",
        type=Path,
        default=Path("results/public/association_rules_validated_cds_public.csv"),
        help="Existing public rule output. Optional; CDS audit is skipped if missing.",
    )
    p.add_argument("--out", type=Path, default=Path("results/bdcc_robustness"))
    p.add_argument("--discovery-end", default="2025-12")
    p.add_argument("--validation-start", default="2026-01")
    p.add_argument("--confidence", type=float, default=0.10)
    p.add_argument("--lift", type=float, default=1.05)
    p.add_argument("--fdr", type=float, default=0.05)
    p.add_argument("--benchmark-scales", default="1,2,5,10")
    return p.parse_args()


def ensure_columns(df: pd.DataFrame, required: set[str], name: str) -> None:
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{name} is missing required columns: {sorted(missing)}")


def read_inputs(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame]:
    baskets = pd.read_csv(args.baskets, dtype={"transaction_id_public": str, "day_id_public": str, "month": str})
    items = pd.read_csv(
        args.items,
        dtype={"transaction_id_public": str, "day_id_public": str, "month": str, "product_id_public": str},
    )
    ensure_columns(
        baskets,
        {
            "transaction_id_public", "day_id_public", "month", "weekday", "service_interval",
            "basket_value_ron", "distinct_products", "multi_product_basket",
        },
        "baskets",
    )
    ensure_columns(
        items,
        {"transaction_id_public", "day_id_public", "month", "product_id_public"},
        "items",
    )
    baskets["month"] = baskets["month"].astype(str)
    items["month"] = items["month"].astype(str)
    baskets["year"] = pd.to_numeric(baskets["month"].str[:4], errors="raise").astype(int)
    baskets["month_no"] = pd.to_numeric(baskets["month"].str[5:7], errors="raise").astype(int)
    baskets["weekday"] = pd.Categorical(baskets["weekday"], categories=WEEKDAYS, ordered=True)
    baskets["service_interval"] = pd.Categorical(
        baskets["service_interval"], categories=SERVICE_INTERVALS, ordered=True
    )
    return baskets, items


def data_audit(baskets: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    n = baskets["transaction_id_public"].nunique()
    p = items["product_id_public"].nunique()
    binary_incidence = items[["transaction_id_public", "product_id_public"]].drop_duplicates().shape[0]
    theoretical_positions = n * p
    theoretical_pairs = p * (p - 1) // 2
    duplicate_binary_rows = len(items) - binary_incidence
    rows = [
        ("baskets", n),
        ("item_rows", len(items)),
        ("binary_product_presences", binary_incidence),
        ("distinct_products", p),
        ("active_public_days", baskets["day_id_public"].nunique()),
        ("months", baskets["month"].nunique()),
        ("theoretical_basket_product_positions", theoretical_positions),
        ("binary_incidence_density", binary_incidence / theoretical_positions if theoretical_positions else np.nan),
        ("theoretical_unordered_product_pairs", theoretical_pairs),
        ("duplicate_transaction_product_rows", duplicate_binary_rows),
        ("full_sample_support_equivalent_to_100_baskets", 100 / n if n else np.nan),
        ("min_basket_value_ron", baskets["basket_value_ron"].min()),
        ("p99_basket_value_ron", baskets["basket_value_ron"].quantile(0.99)),
        ("max_basket_value_ron", baskets["basket_value_ron"].max()),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def build_transactions(items: pd.DataFrame) -> list[tuple[str, ...]]:
    return (
        items.groupby("transaction_id_public", sort=False)["product_id_public"]
        .agg(lambda s: tuple(sorted(set(s.dropna().astype(str)))))
        .tolist()
    )


def pair_counts_from_transactions(transactions: list[tuple[str, ...]], scale: int = 1):
    item_counts: collections.Counter[str] = collections.Counter()
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for _ in range(scale):
        for prod_set in transactions:
            item_counts.update(prod_set)
            pair_counts.update(itertools.combinations(prod_set, 2))
    return item_counts, pair_counts, len(transactions) * scale


def pair_stats_from_transactions(
    transactions: list[tuple[str, ...]],
    min_support: float = 0.0,
) -> pd.DataFrame:
    item_counts, pair_counts, n = pair_counts_from_transactions(transactions)
    min_count = max(1, int(math.ceil(min_support * n)))
    rows = []
    for (a, b), ab in pair_counts.items():
        if ab < min_count:
            continue
        ca, cb = item_counts[a], item_counts[b]
        n11 = ab
        n10 = ca - ab
        n01 = cb - ab
        n00 = n - ca - cb + ab
        support = ab / n
        sup_a = ca / n
        sup_b = cb / n
        lift = support / (sup_a * sup_b) if sup_a > 0 and sup_b > 0 else np.nan
        denom = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
        phi = (n11 * n00 - n10 * n01) / math.sqrt(denom) if denom > 0 else np.nan
        chi2, p = chi2_contingency([[n11, n10], [n01, n00]], correction=False)[:2]
        rows.append((a, b, ab, ca, cb, support, sup_a, sup_b, lift, phi, chi2, p))
    df = pd.DataFrame(
        rows,
        columns=[
            "item_a", "item_b", "pair_count", "count_a", "count_b", "support",
            "support_a", "support_b", "lift_pair", "phi", "chi_square", "p_value",
        ],
    )
    if len(df):
        df["q_bh_pair"] = multipletests(df["p_value"].values, method="fdr_bh")[1]
        df["q_by_pair"] = multipletests(df["p_value"].values, method="fdr_by")[1]
    else:
        df["q_bh_pair"] = pd.Series(dtype=float)
        df["q_by_pair"] = pd.Series(dtype=float)
    return df


def directional_rules(pair_df: pd.DataFrame, n: int) -> pd.DataFrame:
    rows = []
    for r in pair_df.itertuples(index=False):
        for ant, cons, ant_count, cons_count in [
            (r.item_a, r.item_b, r.count_a, r.count_b),
            (r.item_b, r.item_a, r.count_b, r.count_a),
        ]:
            conf = r.pair_count / ant_count if ant_count else np.nan
            cons_sup = cons_count / n if n else np.nan
            lift = conf / cons_sup if cons_sup else np.nan
            rows.append(
                {
                    "antecedent": ant,
                    "consequent": cons,
                    "item_a": r.item_a,
                    "item_b": r.item_b,
                    "pair_count": r.pair_count,
                    "support": r.support,
                    "confidence": conf,
                    "lift": lift,
                    "phi": r.phi,
                    "p_value_pair": r.p_value,
                    "q_bh_pair": r.q_bh_pair,
                    "q_by_pair": r.q_by_pair,
                }
            )
    return pd.DataFrame(rows)


def select_rules(
    rules: pd.DataFrame,
    confidence: float,
    lift: float,
    fdr: float,
    q_col: str = "q_bh_pair",
) -> pd.DataFrame:
    if not len(rules):
        return rules.copy()
    return rules[
        (rules["confidence"] >= confidence)
        & (rules["lift"] >= lift)
        & (rules[q_col] <= fdr)
    ].copy()


def rule_key(df: pd.DataFrame) -> pd.Series:
    return df["antecedent"].astype(str) + "->" + df["consequent"].astype(str)


def discovery_validation(
    baskets: pd.DataFrame,
    items: pd.DataFrame,
    discovery_end: str,
    validation_start: str,
    confidence: float,
    lift: float,
    fdr: float,
):
    disc_ids = set(baskets.loc[baskets["month"] <= discovery_end, "transaction_id_public"])
    val_ids = set(baskets.loc[baskets["month"] >= validation_start, "transaction_id_public"])
    disc_items = items[items["transaction_id_public"].isin(disc_ids)]
    val_items = items[items["transaction_id_public"].isin(val_ids)]
    disc_trans = build_transactions(disc_items)
    val_trans = build_transactions(val_items)

    disc_pairs = pair_stats_from_transactions(disc_trans, BASE_MIN_SUPPORT)
    disc_rules = directional_rules(disc_pairs, len(disc_trans))
    disc_selected = select_rules(disc_rules, confidence, lift, fdr, "q_bh_pair")
    if not len(disc_selected):
        summary = pd.DataFrame([{"metric": "discovered_directional_rules", "value": 0}])
        return summary, pd.DataFrame()

    # Validation tests only the unordered pairs discovered in the discovery period.
    val_all_pairs = pair_stats_from_transactions(val_trans, 0.0)
    val_pair_map = val_all_pairs.set_index(["item_a", "item_b"])
    val_rows = []
    n_val = len(val_trans)
    for r in disc_selected.itertuples(index=False):
        key = tuple(sorted((r.antecedent, r.consequent)))
        if key in val_pair_map.index:
            pr = val_pair_map.loc[key]
            ant_count = pr.count_a if r.antecedent == pr.name[0] else pr.count_b
            cons_count = pr.count_b if r.consequent == pr.name[1] else pr.count_a
            conf_v = pr.pair_count / ant_count if ant_count else np.nan
            cons_sup = cons_count / n_val if n_val else np.nan
            lift_v = conf_v / cons_sup if cons_sup else np.nan
            p_v = pr.p_value
            support_v = pr.support
            phi_v = pr.phi
            pair_count_v = pr.pair_count
        else:
            conf_v = lift_v = support_v = phi_v = np.nan
            p_v = 1.0
            pair_count_v = 0
        val_rows.append(
            {
                "antecedent": r.antecedent,
                "consequent": r.consequent,
                "discovery_support": r.support,
                "discovery_confidence": r.confidence,
                "discovery_lift": r.lift,
                "discovery_phi": r.phi,
                "validation_pair_count": pair_count_v,
                "validation_support": support_v,
                "validation_confidence": conf_v,
                "validation_lift": lift_v,
                "validation_phi": phi_v,
                "validation_p_value": p_v,
            }
        )
    detail = pd.DataFrame(val_rows)
    detail["validation_q_bh"] = multipletests(detail["validation_p_value"].fillna(1.0), method="fdr_bh")[1]
    detail["validation_q_by"] = multipletests(detail["validation_p_value"].fillna(1.0), method="fdr_by")[1]
    detail["retained_direction"] = (
        (detail["validation_support"] >= BASE_MIN_SUPPORT)
        & (detail["validation_confidence"] >= confidence)
        & (detail["validation_lift"] >= lift)
        & (detail["validation_q_bh"] <= fdr)
    )
    detail["lift_above_one"] = detail["validation_lift"] > 1.0

    rho_support = spearmanr(detail["discovery_support"], detail["validation_support"], nan_policy="omit").statistic
    rho_conf = spearmanr(detail["discovery_confidence"], detail["validation_confidence"], nan_policy="omit").statistic
    rho_lift = spearmanr(detail["discovery_lift"], detail["validation_lift"], nan_policy="omit").statistic

    summary_dict = {
        "discovery_baskets": len(disc_trans),
        "validation_baskets": len(val_trans),
        "discovery_month_end": discovery_end,
        "validation_month_start": validation_start,
        "discovered_directional_rules": len(disc_selected),
        "validation_rules_retaining_all_baseline_thresholds": int(detail["retained_direction"].sum()),
        "validation_retention_rate": float(detail["retained_direction"].mean()),
        "validation_rules_with_lift_above_one": int(detail["lift_above_one"].sum()),
        "validation_lift_above_one_rate": float(detail["lift_above_one"].mean()),
        "spearman_support_discovery_vs_validation": rho_support,
        "spearman_confidence_discovery_vs_validation": rho_conf,
        "spearman_lift_discovery_vs_validation": rho_lift,
    }
    summary = pd.DataFrame(summary_dict.items(), columns=["metric", "value"])
    return summary, detail


def threshold_sensitivity(
    full_transactions: list[tuple[str, ...]],
    confidence_grid=(0.05, 0.10, 0.15, 0.20),
    lift_grid=(1.00, 1.05, 1.10, 1.20),
    count_grid=(50, 100, 150, 200),
    fdr=0.05,
):
    n = len(full_transactions)
    item_counts, pair_counts, _ = pair_counts_from_transactions(full_transactions)

    # Compute all pair statistics once for pairs meeting the smallest count threshold.
    rows = []
    for (a, b), ab in pair_counts.items():
        if ab < min(count_grid):
            continue
        ca, cb = item_counts[a], item_counts[b]
        n11, n10, n01, n00 = ab, ca - ab, cb - ab, n - ca - cb + ab
        support = ab / n
        denom = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
        phi = (n11 * n00 - n10 * n01) / math.sqrt(denom) if denom > 0 else np.nan
        chi2, p = chi2_contingency([[n11, n10], [n01, n00]], correction=False)[:2]
        rows.append((a, b, ab, ca, cb, support, phi, chi2, p))
    base_pairs = pd.DataFrame(rows, columns=["item_a", "item_b", "pair_count", "count_a", "count_b", "support", "phi", "chi_square", "p_value"])

    def scenario_set(min_count: int, conf_min: float, lift_min: float):
        psub = base_pairs[base_pairs["pair_count"] >= min_count].copy()
        if not len(psub):
            return set()
        psub["q_bh_pair"] = multipletests(psub["p_value"], method="fdr_bh")[1]
        psub["q_by_pair"] = multipletests(psub["p_value"], method="fdr_by")[1]
        dirs = directional_rules(psub, n)
        selected = select_rules(dirs, conf_min, lift_min, fdr, "q_bh_pair")
        return set(rule_key(selected))

    baseline = scenario_set(100, 0.10, 1.05)
    out = []
    for min_count in count_grid:
        for conf_min in confidence_grid:
            for lift_min in lift_grid:
                s = scenario_set(min_count, conf_min, lift_min)
                union = len(s | baseline)
                jaccard = len(s & baseline) / union if union else 1.0
                baseline_retained = len(s & baseline) / len(baseline) if baseline else np.nan
                out.append(
                    {
                        "min_pair_count": min_count,
                        "min_support": min_count / n,
                        "min_confidence": conf_min,
                        "min_lift": lift_min,
                        "fdr_bh": fdr,
                        "directional_rules": len(s),
                        "jaccard_vs_baseline": jaccard,
                        "baseline_rule_retention": baseline_retained,
                    }
                )
    return pd.DataFrame(out)


def model_tables(baskets: pd.DataFrame):
    reg = baskets.copy()
    formula_nb = "distinct_products ~ C(weekday) + C(service_interval) + C(month_no) + C(year)"
    formula_gamma = "basket_value_ron ~ C(weekday) + C(service_interval) + C(month_no) + C(year)"

    comparisons = []

    # Poisson benchmark, cluster-robust uncertainty by day.
    poisson = smf.glm(formula_nb, data=reg, family=sm.families.Poisson()).fit(
        cov_type="cluster", cov_kwds={"groups": reg["day_id_public"]}
    )
    comparisons.append({"model": "Poisson GLM clustered by day", "aic": poisson.aic, "bic_deviance": getattr(poisson, "bic_deviance", np.nan)})

    # Manuscript baseline: alpha fixed at 1.0, but with clustered SE for a fair comparison.
    nb_fixed = smf.glm(
        formula_nb, data=reg, family=sm.families.NegativeBinomial(alpha=1.0)
    ).fit(cov_type="cluster", cov_kwds={"groups": reg["day_id_public"]})
    comparisons.append({"model": "NB GLM alpha=1.0 clustered by day", "aic": nb_fixed.aic, "bic_deviance": getattr(nb_fixed, "bic_deviance", np.nan)})

    # Estimated-dispersion NB2.
    nb2 = smf.negativebinomial(formula_nb, data=reg).fit(
        method="bfgs", maxiter=1000, disp=False,
        cov_type="cluster", cov_kwds={"groups": reg["day_id_public"]}
    )
    comparisons.append({"model": "NB2 estimated alpha clustered by day", "aic": nb2.aic, "bic_deviance": np.nan})

    params = nb2.params
    conf = nb2.conf_int()
    pvalues = nb2.pvalues
    rows = []
    for term in params.index:
        coef = params[term]
        lo, hi = conf.loc[term]
        is_alpha = term.lower() in {"alpha", "lnalpha"}
        rows.append(
            {
                "term": term,
                "coef": coef,
                "std_error_clustered": nb2.bse[term],
                "p_value_clustered": pvalues[term],
                "IRR": np.nan if is_alpha else math.exp(coef),
                "IRR_ci_low": np.nan if is_alpha else math.exp(lo),
                "IRR_ci_high": np.nan if is_alpha else math.exp(hi),
                "ci_coef_low": lo,
                "ci_coef_high": hi,
            }
        )
    nb2_table = pd.DataFrame(rows)

    alpha_est = params.get("alpha", np.nan)
    comparisons_df = pd.DataFrame(comparisons)
    comparisons_df["estimated_alpha_if_applicable"] = np.nan
    comparisons_df.loc[comparisons_df["model"].str.startswith("NB2"), "estimated_alpha_if_applicable"] = alpha_est
    comparisons_df["mean_distinct_products"] = reg["distinct_products"].mean()
    comparisons_df["variance_distinct_products"] = reg["distinct_products"].var(ddof=1)
    comparisons_df["variance_to_mean_ratio"] = reg["distinct_products"].var(ddof=1) / reg["distinct_products"].mean()

    # Gamma model: full sample and two robustness restrictions.
    p99 = reg["basket_value_ron"].quantile(0.99)
    scenarios = {
        "full_sample": reg,
        "exclude_top_1pct": reg[reg["basket_value_ron"] <= p99].copy(),
        "exclude_top_1pct_and_values_below_1_ron": reg[(reg["basket_value_ron"] <= p99) & (reg["basket_value_ron"] >= 1.0)].copy(),
    }
    gamma_summary = []
    gamma_rows = []
    for name, d in scenarios.items():
        gm = smf.glm(
            formula_gamma,
            data=d,
            family=sm.families.Gamma(link=sm.families.links.Log()),
        ).fit(cov_type="cluster", cov_kwds={"groups": d["day_id_public"]})
        gamma_summary.append(
            {
                "scenario": name,
                "n_baskets": len(d),
                "min_basket_value": d["basket_value_ron"].min(),
                "max_basket_value": d["basket_value_ron"].max(),
                "aic": gm.aic,
            }
        )
        ci = gm.conf_int()
        for term in gm.params.index:
            coef = gm.params[term]
            lo, hi = ci.loc[term]
            gamma_rows.append(
                {
                    "scenario": name,
                    "term": term,
                    "coef": coef,
                    "std_error_clustered": gm.bse[term],
                    "p_value_clustered": gm.pvalues[term],
                    "multiplicative_effect": math.exp(coef),
                    "effect_ci_low": math.exp(lo),
                    "effect_ci_high": math.exp(hi),
                }
            )
    return comparisons_df, nb2_table, pd.DataFrame(gamma_summary), pd.DataFrame(gamma_rows)


def cds_audit(rules_path: Path):
    if not rules_path.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    rules = pd.read_csv(rules_path, sep=";", decimal=",")
    required = {"AR_score", "DVS_score", "CI_score", "OC_score", "IF_score", "TS_score", "CDS_baseline"}
    ensure_columns(rules, required, "rules")

    # Exact reparameterization: original = 15 + 0.7 * empirical_4_component.
    rules["CDS_empirical_4_component"] = 100 * (
        (2 / 7) * rules["AR_score"]
        + (2 / 7) * rules["DVS_score"]
        + (2 / 7) * rules["CI_score"]
        + (1 / 7) * rules["TS_score"]
    )
    rules["CDS_baseline_reconstructed"] = 15 + 0.7 * rules["CDS_empirical_4_component"]
    max_abs_error = (rules["CDS_baseline"] - rules["CDS_baseline_reconstructed"]).abs().max()
    rho = spearmanr(rules["CDS_baseline"], rules["CDS_empirical_4_component"]).statistic
    same_order = np.array_equal(
        np.argsort(-rules["CDS_baseline"].to_numpy(), kind="stable"),
        np.argsort(-rules["CDS_empirical_4_component"].to_numpy(), kind="stable"),
    )
    audit = pd.DataFrame(
        [
            {"metric": "rules", "value": len(rules)},
            {"metric": "OC_unique_values", "value": rules["OC_score"].nunique()},
            {"metric": "IF_unique_values", "value": rules["IF_score"].nunique()},
            {"metric": "constant_points_from_OC_IF", "value": 15.0},
            {"metric": "max_abs_reconstruction_error", "value": max_abs_error},
            {"metric": "spearman_original_vs_empirical4", "value": rho},
            {"metric": "identical_sort_order", "value": bool(same_order)},
        ]
    )

    weights = {
        "baseline_empirical": {"AR": 2 / 7, "DVS": 2 / 7, "CI": 2 / 7, "TS": 1 / 7},
        "equal": {"AR": 0.25, "DVS": 0.25, "CI": 0.25, "TS": 0.25},
        "analytical_heavy": {"AR": 0.40, "DVS": 0.20, "CI": 0.20, "TS": 0.20},
        "commercial_heavy": {"AR": 0.20, "DVS": 0.20, "CI": 0.40, "TS": 0.20},
        "stability_heavy": {"AR": 0.20, "DVS": 0.20, "CI": 0.20, "TS": 0.40},
    }
    base_score = rules["CDS_empirical_4_component"]
    base_top20 = set(base_score.nlargest(min(20, len(rules))).index)
    sens = []
    for name, w in weights.items():
        score = 100 * (
            w["AR"] * rules["AR_score"]
            + w["DVS"] * rules["DVS_score"]
            + w["CI"] * rules["CI_score"]
            + w["TS"] * rules["TS_score"]
        )
        top20 = set(score.nlargest(min(20, len(rules))).index)
        union = base_top20 | top20
        sens.append(
            {
                "weight_scheme": name,
                "w_AR": w["AR"],
                "w_DVS": w["DVS"],
                "w_CI": w["CI"],
                "w_TS": w["TS"],
                "spearman_vs_baseline_empirical": spearmanr(base_score, score).statistic,
                "top20_jaccard_vs_baseline_empirical": len(base_top20 & top20) / len(union) if union else 1.0,
            }
        )
    return audit, pd.DataFrame(sens), rules


def scalability_benchmark(transactions: list[tuple[str, ...]], scales: list[int]) -> pd.DataFrame:
    rows = []
    for scale in scales:
        tracemalloc.start()
        t0 = time.perf_counter()
        item_counts, pair_counts, n = pair_counts_from_transactions(transactions, scale=scale)
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "scale_factor": scale,
                "effective_baskets": n,
                "distinct_products": len(item_counts),
                "observed_unordered_pairs": len(pair_counts),
                "pair_enumeration_seconds": elapsed,
                "peak_python_tracemalloc_mb": peak / (1024 ** 2),
            }
        )
    return pd.DataFrame(rows)




def scalability_benchmark_extended(transactions: list[tuple[str, ...]], scales: list[int]) -> pd.DataFrame:
    """Stress test that increases both transaction volume and catalogue size.

    Each replication receives a disjoint product-ID namespace. This is a synthetic
    computational workload only; it does not create additional empirical observations.
    """
    rows = []
    for scale in scales:
        tracemalloc.start()
        t0 = time.perf_counter()
        item_counts: collections.Counter[str] = collections.Counter()
        pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
        effective_baskets = 0
        for replica in range(scale):
            prefix = f"R{replica:03d}_"
            for transaction in transactions:
                renamed = tuple(prefix + item for item in transaction)
                item_counts.update(renamed)
                pair_counts.update(itertools.combinations(renamed, 2))
                effective_baskets += 1
        elapsed = time.perf_counter() - t0
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "benchmark": "volume_and_catalog_disjoint_replication",
                "scale_factor": scale,
                "effective_baskets": effective_baskets,
                "distinct_products": len(item_counts),
                "observed_unordered_pairs": len(pair_counts),
                "seconds": elapsed,
                "peak_tracemalloc_mb": peak / (1024 ** 2),
            }
        )
    return pd.DataFrame(rows)


def write_summary(out: Path, tables: dict[str, pd.DataFrame]) -> None:
    audit = tables["audit"].set_index("metric")["value"].to_dict()
    dv = tables["discovery_validation"].set_index("metric")["value"].to_dict() if len(tables["discovery_validation"]) else {}
    cds = tables["cds_audit"].set_index("metric")["value"].to_dict() if len(tables["cds_audit"]) else {}
    lines = [
        "# BDCC robustness analysis summary",
        "",
        "## Data audit",
        f"- Baskets: {audit.get('baskets')}",
        f"- Item rows: {audit.get('item_rows')}",
        f"- Distinct products: {audit.get('distinct_products')}",
        f"- Incidence density: {float(audit.get('binary_incidence_density', np.nan)):.6f}",
        "",
        "## Out-of-period rule validation",
    ]
    if dv:
        lines += [
            f"- Discovery directional rules: {dv.get('discovered_directional_rules')}",
            f"- Validation retention rate: {float(dv.get('validation_retention_rate', np.nan)):.3f}",
            f"- Lift > 1 validation rate: {float(dv.get('validation_lift_above_one_rate', np.nan)):.3f}",
            f"- Spearman support: {float(dv.get('spearman_support_discovery_vs_validation', np.nan)):.3f}",
            f"- Spearman confidence: {float(dv.get('spearman_confidence_discovery_vs_validation', np.nan)):.3f}",
            f"- Spearman lift: {float(dv.get('spearman_lift_discovery_vs_validation', np.nan)):.3f}",
        ]
    else:
        lines.append("- No rules passed the discovery thresholds.")
    lines += ["", "## CDS audit"]
    if cds:
        lines += [
            f"- OC unique values: {cds.get('OC_unique_values')}",
            f"- IF unique values: {cds.get('IF_unique_values')}",
            f"- Constant points from OC+IF: {cds.get('constant_points_from_OC_IF')}",
            f"- Spearman original vs four-component reparameterization: {float(cds.get('spearman_original_vs_empirical4', np.nan)):.6f}",
            f"- Identical sort order: {cds.get('identical_sort_order')}",
        ]
    else:
        lines.append("- Existing public rule table not found; CDS audit skipped.")
    lines += [
        "",
        "## Interpretation reminder",
        "These analyses are robustness and validation checks. They do not convert observational associations into causal effects.",
    ]
    (out / "bdcc_robustness_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    baskets, items = read_inputs(args)

    audit = data_audit(baskets, items)
    audit.to_csv(args.out / "00_data_audit.csv", index=False)

    dv_summary, dv_detail = discovery_validation(
        baskets,
        items,
        discovery_end=args.discovery_end,
        validation_start=args.validation_start,
        confidence=args.confidence,
        lift=args.lift,
        fdr=args.fdr,
    )
    dv_summary.to_csv(args.out / "01_discovery_validation_summary.csv", index=False)
    dv_detail.to_csv(args.out / "02_rule_validation_detail.csv", index=False)

    full_trans = build_transactions(items)
    ts = threshold_sensitivity(full_trans, fdr=args.fdr)
    ts.to_csv(args.out / "03_threshold_sensitivity.csv", index=False)

    nb_comp, nb2_coef, gamma_summary, gamma_coef = model_tables(baskets)
    nb_comp.to_csv(args.out / "04_nb_model_comparison.csv", index=False)
    nb2_coef.to_csv(args.out / "05_nb2_clustered_coefficients.csv", index=False)
    gamma_summary.to_csv(args.out / "06_gamma_sensitivity_summary.csv", index=False)
    gamma_coef.to_csv(args.out / "07_gamma_sensitivity_coefficients.csv", index=False)

    cds_a, cds_s, cds_rules = cds_audit(args.rules)
    cds_a.to_csv(args.out / "08_cds_reparameterization.csv", index=False)
    cds_s.to_csv(args.out / "09_cds_weight_sensitivity.csv", index=False)

    scales = [int(x.strip()) for x in args.benchmark_scales.split(",") if x.strip()]
    bench = scalability_benchmark(full_trans, scales)
    bench.to_csv(args.out / "10_scalability_benchmark.csv", index=False)
    bench_extended = scalability_benchmark_extended(full_trans, scales)
    bench_extended.to_csv(args.out / "10_scalability_benchmark_extended.csv", index=False)
    if len(cds_rules):
        cds_rules.to_csv(args.out / "11_reconstructed_rules_cds.csv", index=False)

    tables = {
        "audit": audit,
        "discovery_validation": dv_summary,
        "cds_audit": cds_a,
    }
    write_summary(args.out, tables)
    print(f"Done. Outputs written to: {args.out.resolve()}")


if __name__ == "__main__":
    main()
