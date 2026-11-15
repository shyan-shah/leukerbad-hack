// Reach geometry learned from the live samples (the API does not send start/end).
// Start = first sample of a session; axis and direction = the first axis to move more than LOCK_M;
// length = at least minLen, growing if the hand goes further.

const LOCK_M = 0.03;

export class Track {
  constructor(minLen = 0.30) {
    this.minLen = minLen;
    this.reset();
  }

  reset() {
    this.start = null;
    this.axis = 0;
    this.sign = 1;
    this.locked = false;
    this.len = this.minLen;
    this.lastT = -Infinity;
  }

  // Returns {s, targetS}: progress of hand and target along the reach, 0 = start, 1 = end
  // (both null until the first resting sample of a session).
  update(sample) {
    const { t, pos, target } = sample;
    if (typeof t === "number" && t < this.lastT - 0.5) this.reset();   // t restarts with each session
    if (typeof t === "number") this.lastT = t;
    if (!this.start) {
      // opened mid-rep: wait for rest ("setup" is the walk to the far end before a pull set, also a fine start)
      if (sample.phase && sample.phase !== "idle" && sample.phase !== "setup" && sample.phase !== "calibrate") return { s: null, targetS: null };
      this.start = pos.slice(0, 3);
    }
    if (!this.locked) {
      let best = -1, bestD = LOCK_M;
      for (let i = 0; i < 3; i++) {
        const d = Math.abs(pos[i] - this.start[i]);
        if (d > bestD) { best = i; bestD = d; }
      }
      if (best >= 0) {
        this.axis = best;
        this.sign = pos[best] >= this.start[best] ? 1 : -1;
        this.locked = true;
      }
    }
    const along = p => this.sign * (p[this.axis] - this.start[this.axis]);
    const a = along(pos);
    if (a > this.len) this.len = a;
    return { s: a / this.len, targetS: target ? along(target) / this.len : null };
  }
}
