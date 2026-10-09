from pathlib import Path
from types import SimpleNamespace

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point

from disruptsc.init_pipeline import agents
from disruptsc.init_pipeline.routing import _collect_link_specs
from disruptsc.init_pipeline.supply_chain import _aggregate_import_inputs
from disruptsc.network.commercial_link import CommercialLink
from disruptsc.network.mrio import Mrio, Selection
from disruptsc.params import TransportParams
from disruptsc.run_pipeline.fingerprint import build_stage_fingerprint


def _countries(monkeypatch, per_sector, densities=None):
    rows = [('NOR', 'A01'), ('NOR', 'SVC'), ('DE', 'imports'), ('ALL', 'value_added')]
    columns = [('NOR', 'A01'), ('NOR', 'SVC'), ('DE', 'exports')]
    table = pd.DataFrame(
        0.0, index=pd.MultiIndex.from_tuples(rows),
        columns=pd.MultiIndex.from_tuples(columns),
    )
    table.at[('NOR', 'A01'), ('NOR', 'A01')] = 100
    table.at[('NOR', 'SVC'), ('NOR', 'SVC')] = 100
    table.at[('DE', 'imports'), ('NOR', 'A01')] = 10
    table.at[('DE', 'imports'), ('NOR', 'SVC')] = 20
    mrio = Mrio(
        table,
        monetary_units='EUR',
    )
    cells = {
        (('DE', 'imports'), ('NOR', 'A01')),
        (('DE', 'imports'), ('NOR', 'SVC')),
    }
    selection = Selection(
        1.0, external_buying_countries=('DE',),
        external_selling_countries=('DE',), kept_cells=frozenset(cells),
    )
    country_points = gpd.GeoDataFrame(
        {'region': ['DE'], 'geometry': [Point(0, 0)]}, crs='EPSG:4326'
    )
    monkeypatch.setattr(Path, 'exists', lambda _: True)
    monkeypatch.setattr(agents.gpd, 'read_file', lambda *_: country_points)
    monkeypatch.setattr(
        agents, 'find_nearest_node_id', lambda _nodes, points: np.full(len(points), 7)
    )
    params = SimpleNamespace(
        monetary_units_in_data='EUR', monetary_units_in_model='EUR',
        country_transport_share=0.2, per_sector_import_links=per_sector,
    )
    return agents.create_countries(
        mrio, gpd.GeoDataFrame(geometry=[Point(0, 0)], index=[7], crs='EPSG:4326'),
        Path('countries.geojson'), {'NOR_A01': 5.0} if densities is None else densities,
        'year', params, selection, country_attachment='any',
        sector_table=pd.DataFrame({
            'sector': ['A01', 'SVC'], 'type': ['manufacturing', 'services'],
        }),
        sectors_no_transport=('services',),
    )


@pytest.mark.parametrize(
    ('per_sector', 'service_id', 'goods_id'),
    ((True, 'DE_SVC', 'DE_A01'), (False, 'DE_nontransport_services', 'DE')),
)
def test_services_remain_direct_imports(monkeypatch, per_sector, service_id, goods_id):
    countries = _countries(monkeypatch, per_sector)
    service = countries[service_id]
    assert service.sector_type == 'services'
    assert service.usd_per_ton == 0
    assert countries['DE'].usd_per_ton == 5

    class Buyer:
        agent_type = 'firm'
        virtual = False
        od_point = 8

    graph = nx.DiGraph()
    service_link = CommercialLink(product_type='services', delivery_in_tons=0, order=1)
    goods_link = CommercialLink(product_type='manufacturing', delivery_in_tons=1, order=1)
    graph.add_edge(service, Buyer(), object=service_link)
    graph.add_edge(countries[goods_id], Buyer(), object=goods_link)
    specs = _collect_link_specs(graph, TransportParams(sectors_no_transport=('services',)))
    assert [spec['link'] for spec in specs] == [goods_link]


def test_aggregated_imports_separate_nontransport_types():
    needs = {'DE_A01': 10.0, 'DE_SVC': 20.0, 'FR_A01': 5.0}
    product_types = _aggregate_import_inputs(
        needs, {'DE', 'FR'}, {'A01': 'manufacturing', 'SVC': 'services'}, ('services',)
    )
    assert needs == {
        'DE_imports': 10.0, 'DE_nontransport_services': 20.0, 'FR_imports': 5.0,
    }
    assert product_types == {'DE': 'manufacturing', 'FR': 'manufacturing'}


def test_physical_import_without_density_fails(monkeypatch):
    with pytest.raises(ValueError, match="Physical import product 'A01'.*density"):
        _countries(monkeypatch, True, densities={})


def test_no_transport_setting_invalidates_agent_and_supply_chain_caches():
    configs = (
        {'scope': 'test', 'sectors_no_transport_network': []},
        {'scope': 'test', 'sectors_no_transport_network': ['services']},
    )
    for stage in ('agents', 'sc_network'):
        assert build_stage_fingerprint(configs[0], stage)['hash'] != (
            build_stage_fingerprint(configs[1], stage)['hash']
        )
