#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reproduce core descriptive, entropy, and association-rule results from publication-safe data.

Inputs (default):
  data/public/baskets_public_safe.csv
  data/public/items_public_safe.csv

Outputs (default): results/core_reproduction/
  00_core_data_profile.csv
  01_core_entropy.csv
  02_core_basket_descriptives.csv
  03_core_association_rule_summary.csv
  04_core_association_rules.csv

Association-rule inference is performed at the unordered-pair level. Benjamini-Hochberg
FDR correction is applied once per unordered pair, after which both directions are generated
for confidence interpretation. In this dataset this produces the same q-values as duplicating
each pair-level p-value for the two directions, while making the inferential unit explicit.
"""
from __future__ import annotations

import argparse
import collections
import itertools
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from statsmodels.stats.multitest import multipletests


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Reproduce publication-safe core manuscript results.")
    p.add_argument("--baskets", type=Path, default=Path("data/public/baskets_public_safe.csv"))
    p.add_argument("--items", type=Path, default=Path("data/public/items_public_safe.csv"))
    p.add_argument("--dictionary", type=Path, default=Path("data/public/product_dictionary_public.csv"))
    p.add_argument("--out", type=Path, default=Path("results/core_reproduction"))
    p.add_argument("--min-pair-count", type=int, default=100)
    p.add_argument("--min-confidence", type=float, default=0.10)
    p.add_argument("--min-lift", type=float, default=1.05)
    p.add_argument("--fdr", type=float, default=0.05)
    return p.parse_args()


def entropy(values: pd.Series) -> tuple[float, float, int]:
    values = pd.to_numeric(values, errors="coerce").fillna(0.0)
    values = values[values > 0]
    k = int(len(values))
    total = float(values.sum())
    if total <= 0 or k == 0:
        return math.nan, math.nan, k
    probs = values / total
    h = float(-(probs * np.log(probs)).sum())
    h_norm = float(h / np.log(k)) if k > 1 else 0.0
    return h, h_norm, k


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    baskets = pd.read_csv(args.baskets, dtype={"transaction_id_public": str, "day_id_public": str, "month": str})
    items = pd.read_csv(
        args.items,
        dtype={"transaction_id_public": str, "day_id_public": str, "month": str, "product_id_public": str},
    )

    required_b = {"transaction_id_public", "day_id_public", "month", "basket_value_ron", "distinct_products"}
    required_i = {"transaction_id_public", "product_id_public", "quantity", "line_value_ron"}
    missing_b = required_b - set(baskets.columns)
    missing_i = required_i - set(items.columns)
    if missing_b or missing_i:
        raise ValueError(f"Missing columns: baskets={sorted(missing_b)}, items={sorted(missing_i)}")

    n_baskets = int(baskets["transaction_id_public"].nunique())
    n_products = int(items["product_id_public"].nunique())
    binary_presence = int(items[["transaction_id_public", "product_id_public"]].drop_duplicates().shape[0])
    theoretical_positions = int(n_baskets * n_products)
    density = binary_presence / theoretical_positions

    profile = pd.DataFrame(
        [
            ("baskets", n_baskets),
            ("item_rows", int(len(items))),
            ("binary_product_presences", binary_presence),
            ("duplicate_transaction_product_rows", int(len(items) - binary_presence)),
            ("distinct_products", n_products),
            ("active_public_days", int(baskets["day_id_public"].nunique())),
            ("first_month", str(baskets["month"].min())),
            ("last_month", str(baskets["month"].max())),
            ("theoretical_basket_product_positions", theoretical_positions),
            ("binary_incidence_density", density),
            ("possible_unordered_product_pairs", int(n_products * (n_products - 1) // 2)),
        ],
        columns=["metric", "value"],
    )
    profile.to_csv(args.out / "00_core_data_profile.csv", index=False)

    by_product = items.groupby("product_id_public", as_index=True).agg(
        quantity=("quantity", "sum"), value=("line_value_ron", "sum")
    )
    hq, hnq, kq = entropy(by_product["quantity"])
    hv, hnv, kv = entropy(by_product["value"])
    entropy_table = pd.DataFrame(
        [
            ("quantity", hq, hnq, kq),
            ("value", hv, hnv, kv),
        ],
        columns=["weight", "shannon_entropy", "normalized_entropy", "positive_products"],
    )
    entropy_table.to_csv(args.out / "01_core_entropy.csv", index=False)

    desc = baskets[["basket_value_ron", "distinct_products"]].describe(
        percentiles=[0.25, 0.5, 0.75, 0.90, 0.95, 0.99]
    ).T.reset_index().rename(columns={"index": "metric"})
    if "item_lines" in baskets.columns:
        extra = baskets[["item_lines"]].describe(percentiles=[0.25, 0.5, 0.75, 0.90, 0.95, 0.99]).T.reset_index().rename(columns={"index": "metric"})
        desc = pd.concat([desc, extra], ignore_index=True)
    desc.to_csv(args.out / "02_core_basket_descriptives.csv", index=False)

    basket_sets = items.groupby("transaction_id_public")["product_id_public"].agg(lambda x: sorted(set(x)))
    item_counts: collections.Counter[str] = collections.Counter()
    pair_counts: collections.Counter[tuple[str, str]] = collections.Counter()
    for product_set in basket_sets:
        item_counts.update(product_set)
        pair_counts.update(itertools.combinations(product_set, 2))

    pair_rows = []
    for (a, b), pair_count in pair_counts.items():
        if pair_count < args.min_pair_count:
            continue
        count_a = int(item_counts[a])
        count_b = int(item_counts[b])
        neither = n_baskets - count_a - count_b + pair_count
        table = [[pair_count, count_a - pair_count], [count_b - pair_count, neither]]
        chi2, p_value, _, _ = chi2_contingency(table, correction=False)
        phi = math.sqrt(chi2 / n_baskets)
        support = pair_count / n_baskets
        lift = support / ((count_a / n_baskets) * (count_b / n_baskets))
        pair_rows.append(
            {
                "item_a": a,
                "item_b": b,
                "pair_count": int(pair_count),
                "item_a_count": count_a,
                "item_b_count": count_b,
                "support": support,
                "lift": lift,
                "chi_square": chi2,
                "p_value": p_value,
                "phi": phi,
            }
        )

    pairs = pd.DataFrame(pair_rows)
    if pairs.empty:
        raise RuntimeError("No pairs passed the minimum pair-count threshold.")
    pairs["q_bh"] = multipletests(pairs["p_value"].to_numpy(), method="fdr_bh")[1]

    directional = []
    for r in pairs.itertuples(index=False):
        for antecedent, consequent, antecedent_count, consequent_count in [
            (r.item_a, r.item_b, r.item_a_count, r.item_b_count),
            (r.item_b, r.item_a, r.item_b_count, r.item_a_count),
        ]:
            confidence = r.pair_count / antecedent_count
            directional.append(
                {
                    "antecedent_product_id": antecedent,
                    "consequent_product_id": consequent,
                    "pair_count": r.pair_count,
                    "antecedent_count": antecedent_count,
                    "consequent_count": consequent_count,
                    "support": r.support,
                    "confidence": confidence,
                    "lift": r.lift,
                    "chi_square": r.chi_square,
                    "p_value": r.p_value,
                    "q_bh": r.q_bh,
                    "phi": r.phi,
                }
            )

    rules = pd.DataFrame(directional)
    rules["retained"] = (
        (rules["confidence"] >= args.min_confidence)
        & (rules["lift"] >= args.min_lift)
        & (rules["q_bh"] <= args.fdr)
    )
    retained = rules.loc[rules["retained"]].copy()
    if args.dictionary.exists():
        dictionary = pd.read_csv(args.dictionary, dtype={"product_id_public": str})
        if {"product_id_public", "product_label_en"}.issubset(dictionary.columns):
            label_map = dictionary.drop_duplicates("product_id_public").set_index("product_id_public")["product_label_en"]
            retained.insert(1, "antecedent_label_en", retained["antecedent_product_id"].map(label_map))
            retained.insert(3, "consequent_label_en", retained["consequent_product_id"].map(label_map))
    retained = retained.sort_values(["support", "confidence", "lift"], ascending=[False, False, False])
    retained.to_csv(args.out / "04_core_association_rules.csv", index=False)

    summary = pd.DataFrame(
        [
            ("baskets", n_baskets),
            ("unordered_pairs_with_min_pair_count", int(len(pairs))),
            ("directional_rules_tested_after_pair_screen", int(len(rules))),
            ("retained_directional_rules", int(len(retained))),
            ("min_pair_count", args.min_pair_count),
            ("min_confidence", args.min_confidence),
            ("min_lift", args.min_lift),
            ("bh_fdr_threshold", args.fdr),
        ],
        columns=["metric", "value"],
    )
    summary.to_csv(args.out / "03_core_association_rule_summary.csv", index=False)

    print(f"Core reproduction complete: {len(retained)} retained directional rules.")
    print(f"Outputs written to: {args.out}")


if __name__ == "__main__":
    main()
