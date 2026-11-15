import json

import numpy as np
import pytest

from server.contract import RepResult, Sample, SessionSummary


def _sample():
    return Sample(t=1.23, pos=(0.4, 0.0, 0.3), vel=(0.1, 0.0, 0.0), force=(2.0, -0.5, 0.1),
                  target=(0.45, 0.0, 0.3), dial=0.8, rep_idx=3, simulated=True,
                  phase="out", q=(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6))


def _rep():
    return RepResult(session_id="s1", idx=0, mode="assist", dial=0.9, t_start=1.0, duration_s=4.2,
                     rom_m=0.28, path_err_mean_m=0.01, path_err_max_m=0.02, sparc=-1.7,
                     peak_force_n=9.5, mean_force_n=4.1, contribution=0.4, completed=True,
                     simulated=True, rescued=True)


def _summary():
    return SessionSummary(session_id="s1", patient_id="p1", started_at="2026-11-14T15:00:00",
                          ended_at=None, exercise="reach", n_reps=0, simulated=False)


@pytest.mark.parametrize("make", [_sample, _rep, _summary])
def test_json_round_trip(make):
    obj = make()
    d = json.loads(json.dumps(obj.to_dict()))
    assert type(obj).from_dict(d) == obj


def test_tuples_become_lists():
    d = _sample().to_dict()
    assert isinstance(d["pos"], list) and isinstance(d["q"], list)


def test_v0_records_still_load_with_defaults():
    d = _sample().to_dict()
    del d["phase"], d["q"]
    s = Sample.from_dict(d)
    assert s.phase == "idle" and s.q == ()
    r = _rep().to_dict()
    del r["rescued"]
    assert RepResult.from_dict(r).rescued is False


def test_numpy_values_serialise():
    s = Sample(t=np.float64(0.5), pos=tuple(np.array([0.1, 0.2, 0.3])), vel=(0, 0, 0), force=(0, 0, 0),
               target=(0, 0, 0), dial=np.float32(0.5), rep_idx=np.int64(1), simulated=True)
    json.dumps(s.to_dict())  # must not raise


def test_unknown_keys_ignored():
    d = _summary().to_dict() | {"future_field": 1}
    assert SessionSummary.from_dict(d) == _summary()
