#!/usr/bin/env python3
"""Synthesises the film's music bed and sound effects (pure Python, no numpy) as two stereo WAV stems.
Usage: sound.py motion.json outdir   (motion.json: per-frame [t, ex, [hx,hy,hz], halted, arriving] from the film)."""
import array, json, math, random, struct, sys, wave

SR = 44100
DUR = 122.0
N = int(SR * DUR)
random.seed(7)
TAU = 2 * math.pi


def buf():
    return [array.array('f', bytes(4 * N)), array.array('f', bytes(4 * N))]


def add(dst, t, sig, gain=1.0, pan=0.0):
    """Add a mono signal at time t (seconds) with equal-power pan (-1 left .. 1 right)."""
    i0 = int(t * SR)
    a = (pan + 1) * math.pi / 4
    gl, gr = gain * math.cos(a), gain * math.sin(a)
    L, R = dst
    n = min(len(sig), N - i0)
    for k in range(max(0, -i0), n):
        v = sig[k]
        L[i0 + k] += v * gl
        R[i0 + k] += v * gr


def add_st(dst, t, sl, sr_, gain=1.0):
    i0 = int(t * SR)
    L, R = dst
    n = min(len(sl), N - i0)
    for k in range(max(0, -i0), n):
        L[i0 + k] += sl[k] * gain
        R[i0 + k] += sr_[k] * gain


def note(n):  # midi note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


# ---------- building blocks ----------
def lowpass(sig, fc):
    a = 1 - math.exp(-TAU * fc / SR)
    y = 0.0
    out = array.array('f', sig)
    for i, v in enumerate(sig):
        y += a * (v - y)
        out[i] = y
    return out


def highpass(sig, fc):
    lp = lowpass(sig, fc)
    return array.array('f', (a - b for a, b in zip(sig, lp)))


def noise(n):
    r = random.random
    return array.array('f', (r() * 2 - 1 for _ in range(n)))


def svf_sweep(sig, f_of, q=0.7):
    """State-variable band-pass with a time-varying centre frequency f_of(i)."""
    lo = bp = 0.0
    out = array.array('f', bytes(4 * len(sig)))
    damp = 1 / q
    for i, v in enumerate(sig):
        f = 2 * math.sin(math.pi * min(f_of(i), SR / 6) / SR)
        hi = v - lo - damp * bp
        bp += f * hi
        lo += f * bp
        out[i] = bp
    return out


def env(n, a, d, shape=2.0):
    """Attack (s) then exponential-ish decay over the remaining length."""
    na = max(1, int(a * SR))
    out = array.array('f', bytes(4 * n))
    for i in range(n):
        if i < na:
            out[i] = (i / na)
        else:
            x = (i - na) / max(1, n - na)
            out[i] = (1 - x) ** shape
    return out


def mul(a, b):
    return array.array('f', (x * y for x, y in zip(a, b)))


def sine_sweep(dur, f0, f1, curve=1.0, amp=1.0):
    n = int(dur * SR)
    out = array.array('f', bytes(4 * n))
    ph = 0.0
    for i in range(n):
        x = (i / n) ** curve
        ph += TAU * (f0 + (f1 - f0) * x) / SR
        out[i] = math.sin(ph) * amp
    return out


# ---------- sound effects ----------
def whoosh(dur=1.0, f0=250, f1=3200, f2=500):
    n = int(dur * SR)
    nz = noise(n)
    peak = .55

    def f_of(i):
        x = i / n
        return f0 + (f1 - f0) * (x / peak) if x < peak else f1 + (f2 - f1) * ((x - peak) / (1 - peak))
    s = svf_sweep(nz, f_of, .9)
    e = array.array('f', (math.sin(math.pi * min(1, i / n)) ** 2.2 for i in range(n)))
    return mul(s, e)


def impact(big=1.0):
    n = int((1.6 + big) * SR)
    boom = sine_sweep((1.6 + big), 62, 30, .35)
    boom = mul(boom, env(n, .004, 1, 2.6))
    crack = lowpass(noise(int(.2 * SR)), 2600)
    crack = mul(crack, env(len(crack), .001, 1, 4))
    out = array.array('f', boom)
    for i, v in enumerate(crack):
        out[i] += v * .8
    return out


def thump(f=58, dur=.16):
    s = sine_sweep(dur, f * 1.6, f, .3)
    return mul(s, env(len(s), .003, 1, 2.5))


def tick(f=2400, dur=.03):
    s = highpass(noise(int(dur * SR)), f)
    return mul(s, env(len(s), .0005, 1, 3))


def pop(f=700, dur=.09):
    s = sine_sweep(dur, f * 1.9, f, .25)
    return mul(s, env(len(s), .002, 1, 3))


def bell(f, dur=1.4):
    n = int(dur * SR)
    out = array.array('f', bytes(4 * n))
    for h, a in ((1, 1), (2.01, .45), (3.0, .22), (4.2, .12)):
        w = TAU * f * h / SR
        for i in range(n):
            out[i] += math.sin(w * i) * a * math.exp(-i / SR * (2.2 + h))
    return out


def beep(f, dur=.16):
    n = int(dur * SR)
    w = TAU * f / SR
    out = array.array('f', (((math.sin(w * i) + .3 * math.sin(3 * w * i)) * min(1, i / 200, (n - i) / 400)) for i in range(n)))
    return out


def riser(dur=3.2):
    n = int(dur * SR)
    nz = noise(n)
    s = svf_sweep(nz, lambda i: 300 + 5000 * (i / n) ** 2, 1.2)
    tone = sine_sweep(dur, 180, 1100, 2.0)
    e = array.array('f', ((i / n) ** 2.2 for i in range(n)))
    return array.array('f', ((a * .8 + b * .35) * c for a, b, c in zip(s, tone, e)))


def shimmer(base=1174.7, dur=2.5):
    n = int(dur * SR)
    out = array.array('f', bytes(4 * n))
    for k, r in enumerate((1, 1.5, 2, 2.5198, 3)):
        w = TAU * base * r / SR
        for i in range(n):
            out[i] += math.sin(w * i + k) * math.exp(-i / SR * 1.8) * (.5 + .5 * math.sin(TAU * (5 + k) * i / SR)) * .25
    return out


def step():
    s = lowpass(noise(int(.09 * SR)), 900)
    return mul(s, env(len(s), .002, 1, 3))


# ---------- music ----------
TBL = 2048
SAW = array.array('f', (sum(math.sin(TAU * h * i / TBL) / h for h in range(1, 10)) * .55 for i in range(TBL)))


def pad_loop(notes, length, detune=(-.11, 0, .12), bright=1400):
    n = int(length * SR)
    out = array.array('f', bytes(4 * n))
    for m in notes:
        for d in detune:
            inc = note(m + d) * TBL / SR
            ph = random.random() * TBL
            for i in range(n):
                out[i] += SAW[int(ph) % TBL]
                ph += inc
    out = lowpass(lowpass(out, bright), bright)
    sc = 1 / (len(notes) * len(detune))
    return array.array('f', (v * sc for v in out))


def pluck(m, dur=.55):
    n = int(dur * SR)
    w = TAU * note(m) / SR
    return array.array('f', ((math.sin(w * i) + .35 * math.sin(2 * w * i) + .12 * math.sin(3 * w * i)) * math.exp(-i / SR * 7) * min(1, i / 90) for i in range(n)))


def sub(m, length):
    n = int(length * SR)
    w = TAU * note(m) / SR
    return array.array('f', (math.sin(w * i) * min(1, i / 2000, (n - i) / 2000) for i in range(n)))


def kick():
    s = sine_sweep(.32, 130, 44, .25)
    return mul(s, env(len(s), .002, 1, 2.2))


def clap():
    s = svf_sweep(noise(int(.22 * SR)), lambda i: 1500, 1.5)
    return mul(s, env(len(s), .001, 1, 3.5))


def section_gain(t, pts):
    """Piecewise-linear automation from [(t, g), ...]."""
    if t <= pts[0][0]:
        return pts[0][1]
    for (a, ga), (b, gb) in zip(pts, pts[1:]):
        if t <= b:
            return ga + (gb - ga) * (t - a) / (b - a)
    return pts[-1][1]


def build_music():
    M = buf()
    BAR = 2.4
    # 0-8: low drone with wind
    dr = pad_loop([38, 45], 8.6, bright=380)
    add(M, 0, mul(dr, env(len(dr), 2.5, 1, .6)), .5)
    wind = svf_sweep(noise(int(8.6 * SR)), lambda i: 500 + 250 * math.sin(i / SR * .8), 2)
    add(M, 0, mul(wind, env(len(wind), 3, 1, .8)), .18)
    # 8.2-38: tense B minor -> G, darker pad, pulse bass from 18.2, ticks from 29.7
    tense = [pad_loop([47, 50, 54], BAR * 2, bright=900), pad_loop([43, 47, 50], BAR * 2, bright=900)]
    t = 8.2
    k = 0
    while t < 38.0:
        p = tense[k % 2]
        g = section_gain(t, [(8.2, .35), (18, .45), (30, .55), (36, .6)])
        e = env(len(p), .35, 1, .15)
        add(M, t, mul(p, e), g, -.25)
        add(M, t + .01, mul(p, e), g * .9, .25)
        t += BAR * 2
        k += 1
    pl = pluck(35, .28)
    t = 18.2
    while t < 37.8:
        add(M, t, lowpass(pl, 500), .55)
        t += .3
    t = 29.7
    tk = tick(5000, .025)
    while t < 37.9:
        add(M, t, tk, .1, .4 if int(t / .15) % 2 else -.4)
        t += .15
    # 38.2-117: uplifting D - A - Bm - G
    prog = [[50, 54, 57, 62], [49, 52, 57, 61], [47, 50, 54, 59], [47, 50, 55, 59]]
    roots = [38, 33, 35, 31]
    arps = [[62, 66, 69, 74, 69, 66, 69, 74], [61, 64, 69, 73, 69, 64, 69, 73], [59, 62, 66, 71, 66, 62, 66, 71], [59, 62, 67, 71, 67, 62, 67, 71]]
    pads = [pad_loop(c, BAR, bright=1800) for c in prog]
    subs = [sub(r, BAR) for r in roots]
    pk = {m: pluck(m) for a in arps for m in set(a)}
    pk.update({m + 12: pluck(m + 12, .4) for a in arps for m in set(a)})
    kk, cl = kick(), clap()
    t = 38.2
    bar = 0
    while t < 117.0:
        c = bar % 4
        gp = section_gain(t, [(38.2, .55), (45, .5), (56, .45), (85, .4), (97, .5), (108, .55), (116, .6)])
        e = env(len(pads[c]), .05, 1, .05)
        add(M, t, mul(pads[c], e), gp, -.3)
        add(M, t + .012, mul(pads[c], e), gp, .3)
        if t > 44.8:
            add(M, t, subs[c], section_gain(t, [(44.8, .0), (48, .38), (85, .3), (97, .4)]))
        ga = section_gain(t, [(38.2, .12), (44, .2), (56, .18), (85, .14), (97, .22), (108, .26)])
        for j, m in enumerate(arps[c]):
            add(M, t + j * .3, pk[m], ga, -.35 if j % 2 else .35)
            if t > 102 and j % 2 == 0:
                add(M, t + j * .3 + .15, pk[m + 12], ga * .6, .5 if j % 4 else -.5)
        drums = (45 < t < 85) or (97 < t < 117)
        if drums:
            for b in (0, 1.2):
                add(M, t + b, kk, section_gain(t, [(45, .5), (56, .55), (97, .6), (110, .7)]))
            if t > 102:
                for b in (.6, 1.8):
                    add(M, t + b, cl, .16)
        t += BAR
        bar += 1
    # end: big D major swell
    endp = pad_loop([38, 50, 54, 57, 62, 66], 5.2, bright=2600)
    add(M, 116.9, mul(endp, env(len(endp), .25, 1, 1.6)), .75, -.2)
    add(M, 116.92, mul(endp, env(len(endp), .25, 1, 1.6)), .75, .2)
    add(M, 116.9, sub(26, 5.0), .45)
    return M


def build_sfx(motion):
    S = buf()
    # opening: monitor beeps, the hit, heartbeat
    for t in (.15, .95):
        add(S, t, beep(1046, .12), .18)
    add(S, 1.42, impact(1.0), .9)
    add(S, 1.42, lowpass(noise(int(.6 * SR)), 1800), .0)
    for t in (2.3, 3.25, 4.35):
        add(S, t, thump(55), .7)
        add(S, t + .24, thump(50), .45)
    # day counter 4.8-8 (eased): ticks get slower
    for k in range(34):
        x = k / 34
        t = 4.8 + 3.2 * (1 - (1 - x) ** .5)
        add(S, t, tick(3200, .02), .16, -.2)
    # wipes
    for t in (8.2, 18.2, 29.7, 96.6, 107.6, 117.1):
        add(S, t - .55, whoosh(1.1), .9, -.3)
        add(S, t - .5, whoosh(1.0, 400, 4200, 700), .5, .3)
    # 1.7 billion slam + ring + count ticks
    add(S, 8.6, impact(.6), .75)
    add(S, 8.68, shimmer(1567.98, 1.8), .35)
    for k in range(16):
        add(S, 8.6 + 1.6 * (1 - (1 - k / 16) ** .5), tick(2600, .02), .14)
    for k in range(25):
        add(S, 11.6 + k * .04, pop(420 + k * 6, .05), .12, -.6 + k * .05)
    for k in range(10):
        add(S, 13.2 + k * .08, pop(880 + k * 40, .08), .22, -.5 + k * .1)
    # the 32 dots, then the rain of empty ones
    add(S, 24.1, impact(.2), .45)
    for i in range(32):
        add(S, 20.2 + i * .068, pop(600 + i * 18, .06), .17, -.7 + i * .045)
    for i in range(110):
        add(S, 23.4 + random.random() * 2.3, tick(3000 + random.random() * 3000, .018), .08, random.random() * 1.6 - .8)
    add(S, 23.3, whoosh(1.4, 3000, 900, 300), .35)
    # cards
    for k, t in enumerate((31.0, 31.55, 32.1)):
        add(S, t + .05, thump(80 + k * 10, .2), .6)
        add(S, t + .07, tick(1800, .04), .3, -.4 + k * .4)
    # riser into the reveal, impact and bloom
    add(S, 34.9, riser(3.3), .55)
    add(S, 38.15, impact(1.4), .95)
    add(S, 38.2, shimmer(1174.66, 3.2), .45)
    add(S, 38.45, whoosh(1.2, 120, 900, 200), .35)
    # arrival: footsteps, scan sweep, confirmation chime
    for k in range(6):
        add(S, 44.85 + k * .5, step(), .35, -.2 + k * .08)
    for k in range(4):
        add(S, 50.05 + k * .45, step(), .32, .2)
    sc = sine_sweep(1.5, 520, 1500, 1.0)
    trem = array.array('f', ((.5 + .5 * math.sin(TAU * 14 * i / SR)) * math.sin(math.pi * i / len(sc)) for i in range(len(sc))))
    add(S, 47.9, mul(sc, trem), .12)
    add(S, 49.6, bell(659.25, 1.2), .2, -.1)
    add(S, 49.75, bell(987.77, 1.4), .2, .1)
    # camera cuts
    for t in (56.4, 60.2, 64.2, 67.6, 72.2, 75.2, 78.4):
        add(S, t - .3, whoosh(.55, 600, 5000, 1200), .45, .2)
        add(S, t, tick(1500, .035), .25)
    # muscle card in, and its updates
    add(S, 56.6, whoosh(.6, 300, 2400, 600), .3, .6)
    for t in (56.75, 64.45, 72.45):
        add(S, t, pop(990, .07), .2, .6)
    for k in range(4):
        add(S, 57.25 + k * .1, pop(1320 + k * 90, .05), .1, .6)
    # servo whirr following the real arm motion
    srv = [array.array('f', bytes(4 * N)), array.array('f', bytes(4 * N))]
    pts = []
    for a, b in zip(motion, motion[1:]):
        v = math.dist(a[2], b[2]) * 30
        pts.append((b[0], v))
    ph1 = ph2 = 0.0
    vs = 0.0
    j = 0
    i0, i1 = int(52 * SR), int(97 * SR)
    for i in range(i0, i1):
        t = i / SR
        while j < len(pts) - 1 and pts[j + 1][0] <= t:
            j += 1
        vt = pts[j][1] if j < len(pts) else 0
        vs += (vt - vs) * .0006
        amp = min(1, vs / .35) ** .8
        f = 210 + vs * 700
        ph1 += TAU * f / SR
        ph2 += TAU * f * 2.01 / SR
        v = (math.sin(ph1) * .6 + math.sin(ph2) * .3 + math.sin(ph1 * 3.02) * .12) * amp
        srv[0][i] = v
        srv[1][i] = v
    sl = highpass(srv[0][i0:i1], 120)
    add_st(S, 52, sl, sl, .1)
    # emergency stop: clunk, alarm, release
    add(S, 81.45, thump(70, .25), .7)
    add(S, 81.45, tick(900, .06), .4)
    for k in range(3):
        add(S, 81.55 + k * .4, beep(880, .16), .2)
        add(S, 81.75 + k * .4, beep(660, .16), .2)
    add(S, 84.4, pop(520, .14), .25)
    # the app
    add(S, 85.55, whoosh(1.0, 200, 2600, 500), .55, .3)
    add(S, 86.8, mul(sine_sweep(1.8, 400, 900, 1.0), env(int(1.8 * SR), .3, 1, 1)), .07, .3)
    for k in range(3):
        add(S, 87.4 + k * .12, pop(760 + k * 120, .06), .18, .3)
    for k in range(3):
        add(S, 88.2 + k * .14, tick(2400, .03), .2, .3)
    add(S, 90.6, bell(1318.5, 1.1), .18, .4)
    add(S, 90.78, bell(1760, 1.3), .16, .4)
    add(S, 90.6, whoosh(.8, 500, 3000, 800), .3, .5)
    # why: the week fills up, 3x
    for t in (98.9, 99.1, 100.6, 100.75):
        add(S, t, pop(640, .07), .2, .2)
    for k in range(4):
        add(S, 101.2 + k * .22, pop(880 + k * 110, .08), .25, -.3 + k * .2)
    add(S, 102.2, impact(.5), .7)
    for t in (102.6, 103.5, 104.4):
        add(S, t, tick(2000, .03), .18)
    # vision: the line draws itself
    add(S, 110.4, whoosh(.9, 300, 2000, 400), .3, -.2)
    add(S, 112.0, mul(sine_sweep(2.2, 330, 990, 1.4), env(int(2.2 * SR), .2, 1, .6)), .08, .2)
    # end: logo hit
    add(S, 117.55, impact(1.2), .8)
    add(S, 117.6, shimmer(1174.66, 3.6), .4)
    add(S, 117.7, bell(1174.66, 2.6), .14, -.2)
    add(S, 117.85, bell(1760.0, 2.6), .12, .2)
    return S


def write(path, st, gain=1.0):
    L, R = st
    peak = max(1e-6, max(max(abs(min(L)), abs(max(L))), max(abs(min(R)), abs(max(R)))))
    g = gain * min(1.0, .89 / peak)
    w = wave.open(path, 'wb')
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    out = array.array('h', bytes(4 * N))
    for i in range(N):
        out[2 * i] = int(max(-1, min(1, L[i] * g)) * 32767)
        out[2 * i + 1] = int(max(-1, min(1, R[i] * g)) * 32767)
    w.writeframes(out.tobytes())
    w.close()
    print(path, 'peak', round(peak, 3))


if __name__ == '__main__':
    motion = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    write(out + '/music.wav', build_music())
    write(out + '/sfx.wav', build_sfx(motion))
