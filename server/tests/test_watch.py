from server.watch import View, bar


def _sample(x, dial=0.5, sim=True):
    return {"type": "sample", "t": 1.0, "pos": [x, 0.0, 0.3], "force": [3.0, 4.0, 0.0], "dial": dial,
            "phase": "out", "rep_count": 2, "auto": True, "arm_mode": "compliant", "simulated": sim}


def _rep(i, rescued=False):
    return {"type": "rep", "idx": i, "mode": "assist", "dial": 0.5, "rom_m": 0.25, "path_err_mean_m": 0.01,
            "sparc": -1.8, "peak_force_n": 9.0, "contribution": 0.6, "duration_s": 5.0, "completed": True,
            "rescued": rescued}


def test_bar_marks_position():
    assert bar(-1, -1, 1, width=5) == "[#-|--]"
    assert bar(0, -1, 1, width=5) == "[--#--]"
    assert bar(1, -1, 1, width=5) == "[--|-#]"
    assert bar(5, 0, 1, width=5).endswith("#]")   # clamped high
    assert bar(-5, 0, 1, width=5).startswith("[#")  # clamped low


def test_render_waiting():
    assert "Waiting" in View().render()


def test_render_simulated_and_reps():
    v = View()
    v.update(_sample(0.45))
    v.update(_sample(0.75))
    for i in range(12):
        v.update(_rep(i, rescued=(i == 11)))
    out = v.render()
    assert "SIMULATED" in out and "5.0 N" in out and "100%" in out
    assert len(v.reps) == 10 and "rescued" in out
    assert "   0 assist" not in out and "  11 assist" in out   # only the last 10 shown


def test_real_label():
    v = View()
    v.update(_sample(0.45, sim=False))
    out = v.render()
    assert "REAL ROBOT" in out and "SIMULATED" not in out
