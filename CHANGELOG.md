# Changelog

All notable changes to this reproducibility repository are documented here.

## [1.0.0] - 2026-08-20

Initial reproducibility release prepared for the manuscript **"Mining and Explaining Transactional Patterns with Entropy, Association Rules, and Statistical Models: A Reproducible Workflow for Operational Decision Support"**.

### Included

- Publication-safe basket-level and item-level transaction datasets.
- Public product dictionary with stable anonymous product identifiers and reviewed/public labels.
- Executable public-data core reproduction script.
- Executable BDCC robustness and validation suite.
- Baseline association-rule output containing 1,174 retained directional rules.
- Pair-level Benjamini-Hochberg multiplicity control with directional confidence interpretation.
- Correct binary-incidence audit: 139,394 unique basket-product presences from 139,396 item-level rows.
- Out-of-period rule validation using January-June 2026 as the later validation period.
- Threshold-sensitivity analysis for pair count, confidence, and lift.
- Estimated-dispersion NB2 modelling with day-clustered uncertainty.
- Gamma-log-link robustness analysis with day-clustered uncertainty and value-tail restrictions.
- Exact four-component reparameterization of the empirical Composite Decision Score.
- Alternative score-weight sensitivity analysis.
- Fixed-catalog and expanding-catalog synthetic computational stress tests.
- Publication-ready robustness figures and reference result tables.
- Code licence, data-licensing notice, data dictionary, and reproducibility instructions.

### Reproducibility notes

The repository is designed so that the public core reproduction and robustness analyses can be run directly from the publication-safe CSV files included in `data/public/`. Raw operational databases and private mappings are not required for these public-data checks and are intentionally not distributed.
