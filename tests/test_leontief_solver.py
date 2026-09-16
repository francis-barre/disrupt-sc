import numpy as np
from scipy.sparse import csr_matrix

from disruptsc.config import build_params
from disruptsc.run_pipeline.simulate import _solve_leontief


def test_leontief_solvers_agree():
    matrix = csr_matrix([[1.0, -0.2], [-0.1, 1.0]])
    demand = np.array([1.0, 2.0])
    direct = _solve_leontief(matrix, demand, "direct")
    iterative = _solve_leontief(matrix, demand, "gmres")
    assert np.allclose(iterative, direct, rtol=1e-10, atol=1e-10)


def test_gmres_falls_back_to_direct(monkeypatch):
    import disruptsc.run_pipeline.simulate as simulate

    monkeypatch.setattr(simulate.sp_linalg, "gmres", lambda *args, **kwargs: (None, 1))
    matrix = csr_matrix([[1.0, -0.2], [-0.1, 1.0]])
    result = _solve_leontief(matrix, np.array([1.0, 2.0]), "gmres")
    assert np.allclose(result, [1.42857143, 2.14285714])


def test_unknown_leontief_solver_rejected():
    with np.testing.assert_raises(ValueError):
        build_params({"leontief_solver": "bogus"})
