# Reproducibility Guide

## Recommended environment

Python 3.12 is recommended. Either create the Conda environment from `environment.yml` or install the packages in `requirements.txt`.

### Conda

```bash
conda env create -f environment.yml
conda activate transactional-patterns-bigdata-ml
```

### pip

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

## Run the complete public-data reproduction

From the repository root:

```bash
python src/run_all_public.py
```

This executes two stages.

### Stage 1 — Core reproduction

```bash
python src/analysis/01_reproduce_public_core.py
```

Expected reference checks:

- 31,157 baskets;
- 139,396 item rows;
- 139,394 unique transaction-product presences;
- 710 products;
- normalized quantity entropy approximately 0.708339;
- normalized value entropy approximately 0.797710;
- 1,174 retained directional association rules.

Outputs are written to `results/core_reproduction/`.

### Stage 2 — Robustness and validation

```bash
python src/analysis/02_run_bdcc_robustness.py
```

Expected reference checks include:

- discovery period through 2025-12: 24,467 baskets;
- validation period from 2026-01: 6,690 baskets;
- 1,269 directional discovery rules;
- 625 rules retaining all baseline thresholds in validation;
- validation lift > 1 for 1,188 rules;
- Spearman discovery-validation lift correlation approximately 0.803;
- NB2 estimated alpha approximately 0.4039;
- exact rank preservation under the four-component CDS reparameterization.

Outputs are written to `results/bdcc_robustness/`.

## Runtime note

The pair-enumeration benchmark reports wall-clock runtime and Python-traced peak memory. These values vary by hardware, operating system, Python build, and background load. Structural counts should reproduce; exact runtime values are not expected to be identical.

## Privacy boundary

The public scripts run exclusively on publication-safe derived CSV files. Raw operational DBF files, original identifiers, and private mappings are not required for the public-data reproduction and are not included.
