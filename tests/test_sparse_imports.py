from copy import deepcopy
from types import SimpleNamespace

import numpy as np

from disruptsc.config import build_params
from disruptsc.init_pipeline.sparse_imports import sparsify_import_mixes
from disruptsc.run_pipeline.fingerprint import build_stage_fingerprint


def _fixture():
    countries = {
        "AAA": SimpleNamespace(
            pid="AAA", region="AAA", sector="imports", sector_type="imports"
        ),
        "BBB": SimpleNamespace(
            pid="BBB", region="BBB", sector="imports", sector_type="imports"
        ),
        "CCC": SimpleNamespace(
            pid="CCC", region="CCC", sector="imports", sector_type="imports"
        ),
        "AAA_A": SimpleNamespace(pid="AAA_A", region="AAA", sector="A"),
        "BBB_A": SimpleNamespace(pid="BBB_A", region="BBB", sector="A"),
    }
    buyers = {
        "b1": SimpleNamespace(
            importance=1.0,
            input_mix={"AAA_A": 6.0, "BBB_A": 4.0, "CCC_B": 3.0, "NOR_A": 2.0},
        ),
        "b2": SimpleNamespace(
            importance=2.0, input_mix={"AAA_A": 4.0, "BBB_A": 6.0, "NOR_A": 3.0}
        ),
    }
    return buyers, countries


def _weighted_import_margins(buyers):
    rows = {}
    columns = {"AAA_A": 0.0, "BBB_A": 0.0, "CCC_B": 0.0}
    for buyer_id, buyer in buyers.items():
        rows[buyer_id] = sum(
            buyer.input_mix.get(seller_id, 0.0) for seller_id in columns
        )
        for seller_id in columns:
            columns[seller_id] += buyer.input_mix.get(seller_id, 0.0) * buyer.importance
    return rows, columns


def test_sparse_imports_preserve_weighted_margins_and_domestic_inputs():
    buyers, countries = _fixture()
    before_rows, before_columns = _weighted_import_margins(buyers)

    result = sparsify_import_mixes(
        buyers, countries, "input_mix",
        scale=lambda buyer: buyer.importance, target_mean_suppliers=1.5,
        sector_labels=("A", "B"), seed=0,
    )

    after_rows, after_columns = _weighted_import_margins(buyers)
    assert result["links_after"] < result["links_before"]
    assert result["mean_suppliers"] <= 1.5
    assert np.allclose(list(before_rows.values()), list(after_rows.values()))
    assert np.allclose(list(before_columns.values()), list(after_columns.values()))
    assert [buyer.input_mix["NOR_A"] for buyer in buyers.values()] == [2.0, 3.0]
    assert result["max_row_margin_relative_error"] < 1e-10
    assert result["max_partner_product_margin_relative_error"] < 1e-10


def test_sparse_imports_are_seed_reproducible():
    first, countries = _fixture()
    second = deepcopy(first)
    sparsify_import_mixes(
        first, countries, "input_mix", scale=lambda buyer: buyer.importance,
        target_mean_suppliers=1.5, sector_labels=("A", "B"), seed=7,
    )
    sparsify_import_mixes(
        second, countries, "input_mix", scale=lambda buyer: buyer.importance,
        target_mean_suppliers=1.5, sector_labels=("A", "B"), seed=7,
    )
    assert {key: value.input_mix for key, value in first.items()} == {
        key: value.input_mix for key, value in second.items()
    }


def test_sparse_import_config_keeps_sector_link_setting():
    assert build_params({})[2].sparse_imports is False
    assert build_params({})[2].nb_import_suppliers_per_input == 1.5
    params = build_params({
        "per_sector_import_links": False,
        "sparse_imports": True, "nb_import_suppliers_per_input": 2.0,
    })[2]
    assert params.sparse_imports is True
    assert params.per_sector_import_links is False
    assert params.nb_import_suppliers_per_input == 2.0
    params = build_params({"per_sector_import_links": True})[2]
    assert params.per_sector_import_links is True
    assert params.sparse_imports is False


def test_sparse_aggregated_imports_preserve_buyer_and_country_totals():
    buyers, countries = _fixture()
    for buyer in buyers.values():
        buyer.input_mix = {
            "AAA_imports": buyer.input_mix.pop("AAA_A"),
            "BBB_imports": buyer.input_mix.pop("BBB_A"),
            "NOR_A": buyer.input_mix["NOR_A"],
        }
    before_rows = {
        buyer_id: sum(buyer.input_mix.values()) - buyer.input_mix["NOR_A"]
        for buyer_id, buyer in buyers.items()
    }
    before_columns = {
        country: sum(
            buyer.input_mix.get(f"{country}_imports", 0.0) * buyer.importance
            for buyer in buyers.values()
        )
        for country in ("AAA", "BBB")
    }
    result = sparsify_import_mixes(
        buyers, countries, "input_mix",
        scale=lambda buyer: buyer.importance, target_mean_suppliers=1.0,
        sector_labels=("A", "B"), seed=0,
    )
    after_rows = {
        buyer_id: sum(buyer.input_mix.values()) - buyer.input_mix["NOR_A"]
        for buyer_id, buyer in buyers.items()
    }
    after_columns = {
        country: sum(
            buyer.input_mix.get(f"{country}_imports", 0.0) * buyer.importance
            for buyer in buyers.values()
        )
        for country in ("AAA", "BBB")
    }
    assert result["links_after"] < result["links_before"]
    assert np.allclose(list(before_rows.values()), list(after_rows.values()))
    assert np.allclose(list(before_columns.values()), list(after_columns.values()))
    assert all("NOR_A" in buyer.input_mix for buyer in buyers.values())


def test_sparse_import_setting_invalidates_only_supply_chain_cache():
    dense = {"scope": "test", "sparse_imports": False}
    sparse = {"scope": "test", "sparse_imports": True}
    assert build_stage_fingerprint(dense, "agents")["hash"] == (
        build_stage_fingerprint(sparse, "agents")["hash"]
    )
    assert build_stage_fingerprint(dense, "sc_network")["hash"] != (
        build_stage_fingerprint(sparse, "sc_network")["hash"]
    )


def test_import_supplier_target_invalidates_supply_chain_cache():
    one = {"scope": "test", "nb_import_suppliers_per_input": 1.5}
    two = {"scope": "test", "nb_import_suppliers_per_input": 2.0}
    assert build_stage_fingerprint(one, "sc_network")["hash"] != (
        build_stage_fingerprint(two, "sc_network")["hash"]
    )
