import numpy as np
import pytest

from software.reps import RepDetector, progress, segment_reps

FS = 100.0
START = np.array([0.4, -0.1, 0.2])
END = np.array([0.4, 0.2, 0.2])  # 0.30 m reach along +y


def _min_jerk(n):
    tau = np.linspace(0.0, 1.0, n)
    return 10 * tau**3 - 15 * tau**4 + 6 * tau**5


def _reach(peak=1.0, out_s=1.5, back_s=1.5, rest_s=0.5):
    """Progress profile for one out-and-back reach with rest before and after."""
    rest = np.zeros(int(rest_s * FS))
    out = peak * _min_jerk(int(out_s * FS))
    back = peak * (1 - _min_jerk(int(back_s * FS)))
    return np.concatenate([rest, out, back, rest])


def _to_recording(s, sideways=0.0):
    s = np.asarray(s, dtype=float)
    t = np.arange(len(s)) / FS
    pos = START + np.outer(s, END - START)
    pos[:, 0] += sideways
    return t, pos


def _detector_reps(t, pos, **kw):
    det = RepDetector(START, END, **kw)
    events = [det.update(ti, pi) for ti, pi in zip(t, pos)]
    return det.reps, events


def test_progress_basic():
    pos = np.array([START, END, (START + END) / 2, START - 0.1 * (END - START)])
    s = progress(pos, START, END)
    assert s.shape == (4,)
    np.testing.assert_allclose(s, [0.0, 1.0, 0.5, -0.1], atol=1e-12)


def test_progress_ignores_sideways_offset_and_is_unclamped():
    s = progress(END + np.array([0.05, 0.03, 0.0]), START, END)
    assert s == pytest.approx(1.1)


def test_progress_zero_length_raises():
    with pytest.raises(ValueError):
        progress(np.zeros((3, 3)), START, START)


def test_five_clean_reaches():
    t, pos = _to_recording(np.concatenate([_reach() for _ in range(5)]))
    reps = segment_reps(t, pos, START, END)
    assert len(reps) == 5
    assert all(c for _, _, c in reps)
    for i0, i1, _ in reps:
        s = progress(pos, START, END)
        assert s[i0] > 0.1 and s[i0 - 1] <= 0.1
        assert s[i1] < 0.1 and s[i1 - 1] >= 0.1
        assert i1 > i0


def test_partial_reach_not_completed():
    s = np.concatenate([_reach(), _reach(peak=0.6), _reach()])
    t, pos = _to_recording(s)
    reps = segment_reps(t, pos, START, END)
    assert [c for _, _, c in reps] == [True, False, True]


def test_jitter_around_thresholds_no_extra_reps():
    rng = np.random.default_rng(0)
    s = np.concatenate([_reach(rest_s=1.0) for _ in range(3)])
    # rest at 0.1 (the back threshold) with noise, so rest periods cross it many times
    rest_level = np.where(s < 0.1, 0.1, 0.0)
    s = np.maximum(s, rest_level)
    # hold at 0.9 (the out threshold) at the top of each reach with noise
    s = s + rng.normal(0.0, 0.01, size=s.shape)
    t, pos = _to_recording(s)
    # make sure the noise really crosses both thresholds
    crossings = np.sum(np.diff((s > 0.1).astype(int)) != 0)
    assert crossings > 20
    reps = segment_reps(t, pos, START, END)
    assert len(reps) == 3
    assert all(c for _, _, c in reps)


def test_jitter_at_out_threshold_reports_reached_once():
    rng = np.random.default_rng(1)
    plateau = 0.9 + rng.normal(0.0, 0.01, size=200)
    s = np.concatenate([np.zeros(50), np.linspace(0, 0.9, 100), plateau,
                        np.linspace(0.9, 0, 100), np.zeros(50)])
    t, pos = _to_recording(s)
    reps, events = _detector_reps(t, pos)
    assert events.count("rep_start") == 1
    assert events.count("rep_reached") == 1
    assert events.count("rep_end") == 1
    assert reps == segment_reps(t, pos, START, END)


def test_short_excursion_dropped():
    s = np.concatenate([np.zeros(50), np.full(20, 0.5), np.zeros(50)])  # 0.2 s blip
    t, pos = _to_recording(s)
    assert segment_reps(t, pos, START, END) == []
    reps, events = _detector_reps(t, pos)
    assert reps == []
    assert "rep_end" not in events


def test_unfinished_rep_not_returned():
    s = np.concatenate([_reach(), np.zeros(50), _min_jerk(150)])  # ends while out
    t, pos = _to_recording(s)
    assert len(segment_reps(t, pos, START, END)) == 1


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_detector_agrees_with_segment_reps(seed):
    rng = np.random.default_rng(seed)
    parts = [_reach(peak=p, out_s=rng.uniform(0.8, 2.0), back_s=rng.uniform(0.8, 2.0),
                    rest_s=rng.uniform(0.2, 1.0))
             for p in [1.0, 0.6, 0.95, 0.3, 1.05]]
    s = np.concatenate(parts) + rng.normal(0.0, 0.01, size=sum(map(len, parts)))
    t, pos = _to_recording(s, sideways=0.01)
    expected = segment_reps(t, pos, START, END)
    reps, events = _detector_reps(t, pos)
    assert reps == expected
    assert len(expected) >= 4
    assert events.count("rep_end") == len(expected)
    for i0, i1, completed in expected:
        assert events[i0] == "rep_start"
        assert events[i1] == "rep_end"
        assert ("rep_reached" in events[i0 + 1:i1]) == completed


def test_detector_event_sequence_single_rep():
    t, pos = _to_recording(_reach())
    _, events = _detector_reps(t, pos)
    assert [e for e in events if e] == ["rep_start", "rep_reached", "rep_end"]


def test_bad_shapes_raise():
    with pytest.raises(ValueError):
        segment_reps(np.arange(5.0), np.zeros((4, 3)), START, END)
    with pytest.raises(ValueError):
        segment_reps(np.arange(5.0), np.zeros((5, 2)), START, END)
