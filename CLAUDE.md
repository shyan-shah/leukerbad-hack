# CLAUDE.md — Leukerbad Robotics Hackathon (14–16 Nov)

## Team
- Team is **Shyan, Shiv, Kian, Mat, Gio**. Shyan, Shiv and Kian build the backend and robot. Mat and Gio own the demo, website, pitch and validation. Each coder runs several Claude Code sessions.
- Folders: `robot/` = Kian, `software/` = Shiv, `server/` = Shyan, `demo/` and `business/` = Mat and Gio.
- Start from `context/KICKOFF.md` (and `context/MASTER_PLAN.md` once it exists, which supersedes it).
- You are one of several Claudes working in parallel on this repo. Assume the others are pushing to `main` at the same time.

## Branching
- Always work on and push to `main`. Never leave work on a separate branch.

## Before any work
1. `git pull origin main`
2. Read everything in `/context` (PROJECT.md, TASKS.md, DECISIONS.md, LOG.md).

## Ownership
- Only edit files in the folder owned by your human (see `context/TASKS.md`).
- `context/` is shared: edit it only to append to LOG.md / DECISIONS.md or update your own human's rows in TASKS.md.
- If you need a change in someone else's folder, note it as a blocker in LOG.md instead of editing it.

## Decisions
- Log any scope or architecture decision in `context/DECISIONS.md` with: time, who, what, why.

## "sync" command
When your human says **"sync"**:
1. `git pull origin main`
2. Append 3–5 lines to `context/LOG.md`: what changed, what's next, blockers for the others.
3. Update your human's task status in `context/TASKS.md`.
4. Commit with a clear message.
5. Push to `main`.

If there's a merge conflict, resolve it keeping both people's changes, then tell your human what conflicted and how it was resolved.
