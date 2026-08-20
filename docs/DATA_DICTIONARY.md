# Public Data Dictionary

## `data/public/baskets_public_safe.csv`

| Column | Description |
|---|---|
| `transaction_id_public` | Stable anonymous transaction identifier. |
| `day_id_public` | Stable anonymous active-day identifier used for clustered uncertainty estimates. |
| `month` | Calendar month in `YYYY-MM` format. |
| `weekday` | Weekday name. |
| `hour` | Transaction hour, 0-23. |
| `service_interval` | Operational time-of-day category used in the analysis. |
| `basket_value_ron` | Reconstructed basket value in Romanian lei (RON). |
| `item_lines` | Number of retained item-level lines in the basket. |
| `distinct_products` | Number of distinct public products in the basket. |
| `total_quantity` | Sum of retained item quantities in the basket. |
| `item_level_value_ron` | Sum of retained item-line values in RON. |
| `multi_product_basket` | Indicator for baskets containing at least two distinct products. |
| `value_difference_ron` | Reconciliation difference between basket-level and item-level value. |

## `data/public/items_public_safe.csv`

| Column | Description |
|---|---|
| `transaction_id_public` | Stable anonymous transaction identifier. |
| `day_id_public` | Stable anonymous active-day identifier. |
| `month` | Calendar month in `YYYY-MM` format. |
| `weekday` | Weekday name. |
| `hour` | Transaction hour, 0-23. |
| `service_interval` | Operational time-of-day category. |
| `product_id_public` | Stable anonymous product identifier used in analysis. |
| `canonical_product_id` | Canonical public product identifier. |
| `product_label_en` | Publication-safe English product label; generic placeholder where review is incomplete or redaction is required. |
| `translation_status_public` | Public label review/translation status. |
| `quantity` | Retained item quantity. |
| `unit_price_ron` | Unit price in RON. |
| `line_value_ron` | Item-line value in RON. |

## `data/public/product_dictionary_public.csv`

| Column | Description |
|---|---|
| `product_id_public` | Stable anonymous product identifier. |
| `canonical_product_id` | Canonical public product identifier. |
| `product_label_en` | Publication-safe English label or generic placeholder. |
| `translation_status_public` | Translation/review status. |
| `sensitive_label` | Boolean indicator used during public-label privacy review. |
| `privacy_flags` | Public privacy-review flags describing why additional redaction/review may have been required. |

## Binary basket-product representation

Association-rule analysis treats each product as present at most once in a transaction. Two repeated transaction-product item rows exist in the item-level file, so 139,396 item rows correspond to 139,394 unique binary transaction-product presences.
