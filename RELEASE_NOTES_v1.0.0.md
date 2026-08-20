# v1.0.0 — BDCC Reproducibility Release

This is the first stable reproducibility release associated with the manuscript:

**Mining and Explaining Transactional Patterns with Entropy, Association Rules, and Statistical Models: A Reproducible Workflow for Operational Decision Support**

The release contains publication-safe basket and item data, a public product dictionary, executable analysis scripts, the baseline association-rule output, out-of-period validation, threshold sensitivity, robust count and basket-value models, Composite Decision Score audits, computational stress tests, and supporting figures.

Key reference checks reproduced by this release include 31,157 baskets, 139,396 item rows, 710 products, 139,394 unique basket-product presences, 1,174 retained baseline directional rules, 625 of 1,269 discovery rules retaining the full baseline thresholds in the later validation period, and an estimated NB2 dispersion parameter of approximately 0.4039.

The computational benchmark is intentionally described as a synthetic in-memory stress test. Runtime values are environment-dependent and should not be interpreted as evidence of distributed or web-scale scalability.

Data-use conditions are described separately in `DATA_LICENSE_PENDING.md`; the MIT licence applies to source code only.
