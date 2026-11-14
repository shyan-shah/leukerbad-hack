import pytest

from server.contract import RepResult
from software.adapt import mode_of, next_dial


def _rep(dial=1.0, completed=True, path_err=0.005, duration=3.0, contribution=0.8,
         rescued=False):
    return RepResult(
        session_id="test", idx=0, mode=mode_of(dial), dial=dial, t_start=0.0,
        duration_s=duration, rom_m=0.3, path_err_mean_m=path_err, path_err_max_m=path_err * 2,
        sparc=-1.5, peak_force_n=10.0, mean_force_n=5.0, contribution=contribution,
        completed=completed, simulated=True, rescued=rescued,
    )


def test_five_successes_from_one_reach_quarter():
    d = 1.0
    for _ in range(5):
        d = next_dial(d, _rep(dial=d))
    assert d == pytest.approx(0.25)
    assert d == 0.25


def test_failure_adds_0_10():
    assert next_dial(0.5, _rep(dial=0.5, completed=False)) == pytest.approx(0.6)
    assert next_dial(0.5, _rep(dial=0.5, contribution=0.2)) == pytest.approx(0.6)


def test_rescued_rep_counts_as_failure():
    # otherwise a perfect rep, but rescued: dial goes up, not down
    assert next_dial(0.5, _rep(dial=0.5, rescued=True)) == pytest.approx(0.6)


def test_clamps_at_one():
    assert next_dial(1.0, _rep(dial=1.0, completed=False)) == 1.0
    assert next_dial(0.95, _rep(dial=0.95, completed=False)) == 1.0


def test_clamps_at_auto_floor():
    assert next_dial(-0.6, _rep(dial=-0.6)) == pytest.approx(-0.6)
    assert next_dial(-0.5, _rep(dial=-0.5)) == pytest.approx(-0.6)
    assert next_dial(-0.3, _rep(dial=-0.3), auto_floor=-0.4) == pytest.approx(-0.4)
    # a manual dial below the floor is lifted to the floor in auto
    assert next_dial(-1.0, _rep(dial=-1.0)) == pytest.approx(-0.6)


def test_neither_success_nor_failure_holds():
    # contribution between 0.3 and 0.6 on the assist side
    assert next_dial(0.7, _rep(dial=0.7, contribution=0.45)) == pytest.approx(0.7)
    # completed and good contribution but too slow
    assert next_dial(0.7, _rep(dial=0.7, duration=7.0)) == pytest.approx(0.7)
    # path error too large
    assert next_dial(0.7, _rep(dial=0.7, path_err=0.02)) == pytest.approx(0.7)


def test_resist_side_success_ignores_contribution_over_0_6():
    assert next_dial(-0.2, _rep(dial=-0.2, contribution=0.5)) == pytest.approx(-0.35)
    # on the assist side the same rep would hold
    assert next_dial(0.2, _rep(dial=0.2, contribution=0.5)) == pytest.approx(0.2)


def test_crossing_zero_is_exactly_transparent():
    d = next_dial(0.15, _rep(dial=0.15))
    assert d == 0.0
    assert mode_of(d) == "transparent"


def test_mode_of():
    assert mode_of(1.0) == "assist"
    assert mode_of(0.05) == "assist"
    assert mode_of(0.0) == "transparent"
    assert mode_of(-0.0) == "transparent"
    assert mode_of(-0.05) == "resist"
    assert mode_of(-1.0) == "resist"
