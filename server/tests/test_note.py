from server.contract import RepResult, SessionSummary
from server.note import HEADER, session_note


def _rep(idx, **kw):
    base = dict(session_id="s", idx=idx, mode="assist", dial=0.8 - 0.1 * idx, t_start=float(idx), duration_s=5.0,
                rom_m=0.25, path_err_mean_m=0.02, path_err_max_m=0.04, sparc=-2.0, peak_force_n=10.0,
                mean_force_n=4.0, contribution=0.5, completed=True, simulated=True, rescued=False)
    base.update(kw)
    return RepResult(**base)


def _summary(sim=True):
    return SessionSummary(session_id="s", patient_id="p", started_at="2026-11-14T15:00:00",
                          ended_at="2026-11-14T15:20:00", exercise="reach_line", n_reps=3, simulated=sim)


def test_header_and_simulated_label():
    note = session_note(_summary(), [_rep(0)])
    assert note.splitlines()[0] == HEADER
    assert "SIMULATED DATA" in note.splitlines()[1]


def test_real_session_has_no_simulated_label():
    assert "SIMULATED" not in session_note(_summary(sim=False), [_rep(0, simulated=False)])


def test_counts_flags_and_best():
    reps = [_rep(0), _rep(1, completed=False, rescued=True, rom_m=0.15), _rep(2, rom_m=0.29)]
    note = session_note(_summary(), reps)
    assert "3 started, 2 completed" in note
    assert "1 rep(s) needed extra assistance" in note
    assert "1 rep(s) did not reach the end" in note
    rom_line = next(line for line in note.splitlines() if line.startswith("Range of motion"))
    assert "29.0 cm" in rom_line  # best ROM is the max


def test_change_vs_previous():
    prev = [_rep(0, path_err_mean_m=0.03, contribution=0.3)]
    note = session_note(_summary(), [_rep(0)], previous=prev)
    err_line = next(line for line in note.splitlines() if line.startswith("Path error, mean"))
    assert "-1.0 cm (better)" in err_line
    c_line = next(line for line in note.splitlines() if line.startswith("Own contribution"))
    assert "+20 pts (better)" in c_line


def test_no_reps():
    assert "No repetitions recorded." in session_note(_summary(), [])


def test_no_diagnosis_words():
    note = session_note(_summary(), [_rep(0), _rep(1)]).lower()
    for word in ("diagnos", "recovered", "prognosis", "should increase", "recommend"):
        assert word not in note
