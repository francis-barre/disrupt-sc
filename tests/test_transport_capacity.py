from disruptsc.init_pipeline.transport import _apply_default_capacities
from disruptsc.network.transport_network import TransportNetwork


def test_default_capacity_does_not_replace_source_capacity():
    network = TransportNetwork()
    network.add_edge(1, 2, type="roads", capacity=7)
    network.add_edge(2, 3, type="roads")

    _apply_default_capacities(network, {"roads": 100}, ["container"], "day")

    assert network[1][2]["capacity"] == 7
    assert network[2][3]["capacity"] == 100
