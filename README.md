# Transactional Pattern Mining for Operational Decision Support

Reproducibility repository for the manuscript:

**Mining and Explaining Transactional Patterns with Entropy, Association Rules, and Statistical Models: A Reproducible Workflow for Operational Decision Support**

**Authors**
- Marian Pompiliu Cristescu — ORCID: https://orcid.org/0000-0003-3638-4379
- Ioana Petrea — ORCID: https://orcid.org/0009-0009-3600-7857

**Manuscript status:** prepared for submission to *Big Data and Cognitive Computing (BDCC)*, Special Issue **Machine Learning Applications for Big Data Analysis**.

**Repository:** https://github.com/petreaioana/transactional-patterns-bigdata-ml  
**Reproducibility release:** `v1.0.0`  
**Release date:** 20 August 2026  
**Article DOI:** pending publication  
**Archived release DOI:** pending archival deposit

## Purpose

This repository contains a publication-safe reproducibility package for the associated manuscript. It provides derived transaction data, product identifiers and reviewed public labels, code that can be executed directly on the public datasets, reference result tables, robustness analyses, and figures.

The workflow combines deterministic data-quality checks, sparse basket reconstruction, Shannon entropy, association-rule mining, multiplicity-controlled statistical screening, generalized linear models, out-of-period validation, sensitivity analysis, and transparent rule prioritization.

The empirical dataset contains:

- **31,157 transaction baskets**;
- **139,396 retained item-level sales lines**;
- **710 distinct products**;
- **762 active sales days**;
- observation period from **20 May 2024 to 28 June 2026**.

For binary basket-product analysis, repeated occurrences of the same product inside the same transaction are collapsed. The resulting sparse incidence representation contains **139,394 unique basket-product presences** over **22,121,470 potential basket-product positions**, corresponding to an incidence density of approximately **0.63013%**.

## Repository structure

```text
transactional-patterns-bigdata-ml/
├── README.md
├── CITATION.cff
├── CHANGELOG.md
├── RELEASE_NOTES_v1.0.0.md
├── LICENSE-CODE
├── DATA_LICENSE_NOTICE.md
├── requirements.txt
├── environment.yml
├── SHA256SUMS.txt
├── data/
│   └── public/
│       ├── baskets_public_safe.csv
│       ├── items_public_safe.csv
│       └── product_dictionary_public.csv
├── src/
│   ├── run_all_public.py
│   └── analysis/
│       ├── 01_reproduce_public_core.py
│       └── 02_run_bdcc_robustness.py
├── results/
│   ├── public/
│   │   └── association_rules_validated_cds_public.csv
│   ├── core_reproduction/
│   └── bdcc_robustness/
├── figures/
│   └── bdcc_robustness/
└── docs/
    ├── DATA_DICTIONARY.md
    └── REPRODUCIBILITY.md
```

## Publication-safe datasets

The public inputs are stored under `data/public/`.

`baskets_public_safe.csv` contains one row per reconstructed transaction basket with anonymous transaction/day identifiers, month, weekday, hour, service interval, basket value, item-line count, number of distinct products, total quantity, item-level value, multi-product flag, and the value reconciliation difference.

`items_public_safe.csv` contains publication-safe item-level lines with anonymous transaction/day identifiers, temporal descriptors, public product identifiers and labels, quantity, unit price, and line value.

`product_dictionary_public.csv` maps public product identifiers to canonical public identifiers, publication-safe English labels, translation-review status, and privacy-review flags.

Raw FoxPro files, original transaction identifiers, private POS product labels, operator/waiter identifiers, table identifiers, private mappings, and other operational identifiers are not included.

## Core reproduction

Run from the repository root:

```bash
python src/analysis/01_reproduce_public_core.py
```

This regenerates the publication-safe core tables under `results/core_reproduction/`, including the data profile, entropy estimates, basket descriptives, and the baseline association-rule set.

The baseline association-rule specification is:

- minimum unordered-pair count: **100 baskets**;
- minimum confidence: **0.10**;
- minimum lift: **1.05**;
- Benjamini-Hochberg false-discovery-rate threshold: **q <= 0.05**.

Under this specification, the public-data reconstruction retains **1,174 directional rules**.

Inference is performed at the unordered-pair level. Each qualifying pair is tested once, Benjamini-Hochberg correction is applied to the pair-level p-values, and the two rule directions are then generated for confidence interpretation. Because every unordered pair has exactly two directions with the same pair-level p-value, this formulation is mathematically equivalent to duplicating every p-value twice before Benjamini-Hochberg correction, while making the inferential unit explicit.

## Robustness and validation suite

Run:

```bash
python src/analysis/02_run_bdcc_robustness.py
```

The default inputs are:

```text
data/public/baskets_public_safe.csv
data/public/items_public_safe.csv
results/public/association_rules_validated_cds_public.csv
```

The outputs are written to `results/bdcc_robustness/`.

### Out-of-period validation

Rules are discovered using May 2024 through December 2025 and re-evaluated using January through June 2026.

Reference results:

- discovery baskets: **24,467**;
- validation baskets: **6,690**;
- discovered directional rules: **1,269**;
- rules retaining all baseline thresholds in validation: **625 (49.25%)**;
- rules retaining lift > 1 in validation: **1,188 (93.62%)**;
- Spearman support correlation: **0.846**;
- Spearman confidence correlation: **0.849**;
- Spearman lift correlation: **0.803**.

These results indicate substantial persistence in relative association strength together with meaningful temporal drift in strict threshold retention.

### Threshold sensitivity

The baseline contains **1,174 rules**. Moderate changes in the lift threshold have little effect on the retained set: a minimum lift of 1.10 retains 1,173 rules, and a minimum lift of 1.20 retains 1,152 rules. Frequency and confidence thresholds have a larger effect, which is documented in `03_threshold_sensitivity.csv`.

### Count-model robustness

Distinct-products-per-basket is overdispersed, with a variance-to-mean ratio of approximately **3.88**.

Reference AIC values are:

- Poisson GLM: **182,640.6**;
- Negative Binomial GLM with fixed alpha = 1: **160,519.1**;
- estimated-dispersion NB2: **154,216.3**;
- estimated NB2 alpha: **0.4039**.

The robustness specification uses estimated-dispersion NB2 with standard errors clustered by public day identifier.

### Basket-value robustness

Gamma GLMs with log link are estimated with day-clustered standard errors for the full sample, after excluding the top 1% of basket values, and after additionally excluding basket values below 1 RON. The late-evening multiplicative association remains positive and statistically supported across all three specifications, while its magnitude changes with treatment of extreme values.

### Composite Decision Score audit

The baseline Composite Decision Score contains two components—operational controllability and implementation feasibility—that are fixed at 0.50 for every rule. Their combined contribution is therefore a constant 15 points.

The empirical four-component form is:

```text
CDS4 = 100 × [(2/7)AR + (2/7)DVS + (2/7)CI + (1/7)TS]
```

and:

```text
CDS_baseline = 15 + 0.70 × CDS4
```

The transformation is strictly monotonic, so the rule ordering is exactly preserved. Alternative empirical weighting schemes are reported in `09_cds_weight_sensitivity.csv`.

### Computational stress test

The sparse pair-enumeration procedure is evaluated using synthetic workload replication. One benchmark increases transaction volume while keeping the catalogue fixed; the extended benchmark uses disjoint product namespaces so transaction volume, catalogue size, and observed pair count increase together.

At the 10× extended setting the workload contains **311,570 effective baskets, 7,100 products, and 257,310 observed unordered pairs**. Runtime is hardware-dependent and is therefore reported as an environment-specific computational measurement rather than a universal performance claim.

These tests do **not** demonstrate distributed, streaming, or web-scale performance and do not create additional empirical observations.

## One-command public reproduction

To run both public-data stages sequentially:

```bash
python src/run_all_public.py
```

The scripts do not modify the source datasets.

## Reproducibility boundaries

The study is observational and single-organization. Association rules describe co-occurrence and should not be interpreted causally. The generalized linear models estimate adjusted associations, not treatment effects. Out-of-period validation evaluates temporal persistence within the same organization and does not establish population-level generalizability. The scalability analysis is a synthetic computational stress test rather than evidence of distributed-system scalability.

## Data confidentiality and licensing

Code and data-use conditions are separated intentionally.

The source code is distributed under the MIT License in `LICENSE-CODE`.

The publication-safe derived datasets and analytical result tables are provided for scientific transparency, manuscript review, and reproducibility assessment under the conditions in `DATA_LICENSE_NOTICE.md`. Their presence in this repository does not constitute an unrestricted open-data licence.

No licence is granted through this repository for raw DBF data, private mappings, original POS labels, internal identifiers, or other non-public operational records.

## Citation and versioning

`v1.0.0` is the first reproducibility release for this repository and is intended to serve as the stable snapshot associated with the submitted manuscript. Citation metadata are provided in `CITATION.cff`.

If an archival DOI is assigned to this release, the DOI should be used in the manuscript and repository citation.
