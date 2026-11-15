import json

from software import strength_model as sm


def test_new_state_and_json():
    assert sm.new_state() == {"v": 1, "fraction": 0.5, "sets": 0}
    json.dumps(sm.update(sm.new_state(), [{"completed": True, "rescued": False, "duration_s": 3.0}]))


def test_weak_medium_strong_get_clearly_different_resistances():
    r = [sm.resistance_for(f, sm.new_state(), 15.0)["resistance_n"] for f in (4.0, 14.0, 28.0)]
    assert r == [3.0, 7.0, 14.0]
    out = sm.resistance_for(50.0, sm.new_state(), 15.0)
    assert out["resistance_n"] == 15.0 and out["dial"] == -1.0 and out["fraction"] == 0.5


def test_easy_set_raises_and_hard_set_lowers_within_bounds():
    easy = [{"completed": True, "rescued": False, "duration_s": 3.0}] * 5
    hard = easy[:4] + [{"completed": False, "rescued": True, "duration_s": 9.0}]
    s = sm.new_state()
    assert sm.update(s, easy)["fraction"] > 0.5 > sm.update(s, hard)["fraction"]
    assert sm.update(s, []) == s and s == sm.new_state()
    up, down = s, s
    for _ in range(20):
        up, down = sm.update(up, easy), sm.update(down, hard)
    assert up["fraction"] == 0.8 and down["fraction"] == 0.3 and up["sets"] == 20
