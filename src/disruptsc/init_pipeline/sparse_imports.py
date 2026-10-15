"""Sparse import links with exact margins."""

from itertools import combinations
import logging

import numpy as np


_RAS_ITERATIONS = 1000
_RAS_TOLERANCE = 1e-7
_MAX_CYCLE_PIVOTS = 2_000_000


def sparsify_import_mixes(
    buyers, country_agents, value_key, *, scale, target_mean_suppliers,
    sector_labels=(), seed=None,
):
    """Prune import links, preserving buyer and country-product totals.

    Import keys are matched by exact country-sector seller IDs or exact
    parent-country plus MRIO-sector labels. Domestic inputs are left untouched;
    cells without a sector seller retain the model's existing parent-country
    fallback. The caller applies import-distance localization first, so pruning
    preserves those localized margins without changing the dense path.
    """
    product_by_import_key = {
        country.pid: country.sector
        for country in country_agents.values()
        if country.pid != country.region
    }
    for country in country_agents.values():
        if country.pid == country.region and country.sector_type == "imports":
            product_by_import_key[f"{country.pid}_imports"] = "imports"
            for sector in sector_labels:
                product_by_import_key[f"{country.pid}_{sector}"] = sector

    groups = {}
    for buyer_id, buyer in sorted(buyers.items()):
        values = getattr(buyer, value_key)
        for supplier_id, amount in values.items():
            product = product_by_import_key.get(supplier_id)
            if product is None or amount <= 0:
                continue
            groups.setdefault(product, {}).setdefault(buyer_id, {})[
                supplier_id
            ] = float(amount)

    rng = np.random.RandomState(seed)
    buyers_products = 0
    links_before = 0
    links_after = 0
    max_row_error = 0.0
    max_partner_product_error = 0.0

    for product, source_rows in sorted(groups.items()):
        buyer_ids = sorted(source_rows)
        supplier_ids = sorted({
            supplier_id
            for cells in source_rows.values()
            for supplier_id in cells
        })
        supplier_index = {supplier_id: j for j, supplier_id in enumerate(supplier_ids)}
        scales = np.array([float(scale(buyers[buyer_id])) for buyer_id in buyer_ids])
        raw = np.zeros((len(buyer_ids), len(supplier_ids)), dtype=float)
        for i, buyer_id in enumerate(buyer_ids):
            for supplier_id, amount in source_rows[buyer_id].items():
                raw[i, supplier_index[supplier_id]] = amount

        weighted = raw * scales[:, None]
        row_targets = weighted.sum(axis=1)
        column_targets = weighted.sum(axis=0)
        matrix = weighted.copy()
        for _ in range(_RAS_ITERATIONS):
            row_sums = matrix.sum(axis=1)
            matrix *= np.divide(
                row_targets, row_sums,
                out=np.ones_like(row_targets), where=row_sums > 0,
            )[:, None]
            column_sums = matrix.sum(axis=0)
            matrix *= np.divide(
                column_targets, column_sums,
                out=np.ones_like(column_targets), where=column_sums > 0,
            )[None, :]
            row_error = np.max(
                np.abs(matrix.sum(axis=1) - row_targets)
                / np.maximum(row_targets, 1e-12)
            )
            column_error = np.max(
                np.abs(matrix.sum(axis=0) - column_targets)
                / np.maximum(column_targets, 1e-12)
            )
            if max(row_error, column_error) < _RAS_TOLERANCE:
                break
        if max(row_error, column_error) >= _RAS_TOLERANCE:
            raise ValueError(f"Import RAS did not converge for {product!r}")

        target_links = int(round(target_mean_suppliers * len(buyer_ids)))
        links = int(np.count_nonzero(matrix))
        pairs = list(combinations(range(len(supplier_ids)), 2))
        pivots = 0
        while links > target_links and pivots < _MAX_CYCLE_PIVOTS:
            rng.shuffle(pairs)
            pass_pivots = 0
            for left, right in pairs:
                shared_rows = np.flatnonzero(
                    (matrix[:, left] > 0) & (matrix[:, right] > 0)
                )
                rng.shuffle(shared_rows)
                paired_rows = shared_rows[:len(shared_rows) // 2 * 2].reshape(-1, 2)
                removed, processed = _pivot_cycle(
                    matrix, row_targets, paired_rows[:, 0], paired_rows[:, 1],
                    left, right, max_cycles=_MAX_CYCLE_PIVOTS - pivots,
                    links_to_remove=links - target_links,
                )
                links -= removed
                pivots += processed
                pass_pivots += processed
                if links <= target_links or pivots >= _MAX_CYCLE_PIVOTS:
                    break
            if pass_pivots == 0:
                break

        final_rows = matrix.sum(axis=1)
        final_columns = matrix.sum(axis=0)
        row_error = float(np.max(
            np.abs(final_rows - row_targets) / np.maximum(row_targets, 1e-12)
        ))
        column_error = float(np.max(
            np.abs(final_columns - column_targets) / np.maximum(column_targets, 1e-12)
        ))
        max_row_error = max(max_row_error, row_error)
        max_partner_product_error = max(max_partner_product_error, column_error)

        for buyer_id, cells in source_rows.items():
            values = getattr(buyers[buyer_id], value_key)
            for supplier_id in cells:
                del values[supplier_id]
        for i, buyer_id in enumerate(buyer_ids):
            values = getattr(buyers[buyer_id], value_key)
            for j, supplier_id in enumerate(supplier_ids):
                if matrix[i, j] > 0:
                    values[supplier_id] = float(matrix[i, j] / scales[i])

        buyers_products += len(buyer_ids)
        links_before += int(np.count_nonzero(raw))
        links_after += int(np.count_nonzero(matrix))

    result = {
        "buyers_products": buyers_products,
        "links_before": links_before,
        "links_after": links_after,
        "mean_suppliers": links_after / buyers_products if buyers_products else 0.0,
        "max_row_margin_relative_error": max_row_error,
        "max_partner_product_margin_relative_error": max_partner_product_error,
    }
    logging.info(
        "Sparse %s import links: %s buyer-products, %s -> %s links; "
        "mean suppliers %.3f; max margin errors %.2g / %.2g",
        value_key, buyers_products, links_before, links_after,
        result["mean_suppliers"], max_row_error, max_partner_product_error,
    )
    return result


def _pivot_cycle(matrix, row_targets, rows_i, rows_k, j, l, *, max_cycles,
                 links_to_remove):
    """Apply independent 2x2 pivots as a batch, stopping at the old limits."""
    count = min(len(rows_i), max_cycles)
    if count == 0:
        return 0, 0

    rows_i, rows_k = rows_i[:count], rows_k[:count]
    a, b = matrix[rows_i, j].copy(), matrix[rows_i, l].copy()
    c, d = matrix[rows_k, j].copy(), matrix[rows_k, l].copy()
    diagonal = np.minimum(a / row_targets[rows_i], d / row_targets[rows_k]) <= np.minimum(
        b / row_targets[rows_i], c / row_targets[rows_k]
    )
    delta = np.where(diagonal, np.minimum(a, d), np.minimum(b, c))
    new_a = np.where(diagonal, a - delta, a + delta)
    new_b = np.where(diagonal, b + delta, b - delta)
    new_c = np.where(diagonal, c + delta, c - delta)
    new_d = np.where(diagonal, d - delta, d + delta)
    removed = np.column_stack((new_a == 0, new_b == 0, new_c == 0, new_d == 0)).sum(axis=1)
    cumulative_removed = np.cumsum(removed)
    count = min(count, int(np.searchsorted(cumulative_removed, links_to_remove)) + 1)

    matrix[rows_i[:count], j] = new_a[:count]
    matrix[rows_i[:count], l] = new_b[:count]
    matrix[rows_k[:count], j] = new_c[:count]
    matrix[rows_k[:count], l] = new_d[:count]
    return int(cumulative_removed[count - 1]), count
