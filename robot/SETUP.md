# robot/SETUP.md — arm laptop and workspace setup (Kian)

Two parts: (1) the arm laptop's Python environment, (2) the physical setup for K4
(chair, table, start pose), which is still to be measured on the arm.

## 1. Arm laptop: Python environment

The venv lives **outside the repo and outside OneDrive** at `C:\venvs\leukerbad`.
OneDrive syncing a venv breaks it (locked files, half-synced packages), so don't put
it under `Documents`.

### Create it (once per laptop)
PowerShell, needs [uv](https://docs.astral.sh/uv/):
```powershell
uv venv C:\venvs\leukerbad --python 3.12
C:\venvs\leukerbad\Scripts\activate
python --version            # expect Python 3.12.x
```
Python 3.12 is the team decision (DECISIONS.md): there is no Windows `flexivrdk` wheel for 3.14.

### Install packages
Run from the repo root with the venv active:
```powershell
uv pip install pytest numpy
python -m pytest robot/tests -q     # offline arm tests, no robot needed
```
To drive the arm the venv also needs the RDK: `uv pip install -r robot/requirements.txt`
(`flexivrdk==1.7.*` plus numpy). Robot software v3.9.3 goes with **flexivrdk 1.7.0**; never a
plain `pip install flexivrdk` (2.x is a different robot family, 1.9.x does not match this
robot). On 14-15 Nov the arm was driven from Shyan's laptop (`C:\venvs\flexiv17`, see
`server/hw/README.md`). Only one laptop drives the arm at a time.

### Firewall (McAfee on Kian's laptop)
A uv venv's `Scripts\python.exe` is a launcher: it starts the real interpreter as a
child process, and **that** process opens the network connections. Allow both:

1. `C:\venvs\leukerbad\Scripts\python.exe`
2. `C:\Users\kianv\AppData\Roaming\uv\python\cpython-3.12.16-windows-x86_64-none\python.exe`
   (find yours with `python -c "import sys; print(sys._base_executable)"`; resolve any
   `cpython-3.12-...` junction to the full `3.12.16` folder)

McAfee: **My Protection → Firewall → Internet connections for programs → Add → Browse**
to each exe, set Access to **Incoming and outgoing**, **Save**. If it's still blocked, mark the
robot Ethernet network as trusted under Firewall → Net Guard / network connections.
On a laptop using Windows Defender Firewall instead, allow the same two exes there.

Network itself (static IP, Remote mode, licence) is covered in `robot/RUNBOOK.md`.

## 2. Workspace and start pose (K4) — TODO, measure on the arm

All values below are unmeasured. When measured, copy them into `robot/config.json`
and remove the matching key from its `placeholders` list.

- Chair position: TODO
- Table height: TODO
- Arm base position: TODO
- Which base axis is the reach: TODO
- Start pose (`tcp_pose` and `q`): TODO
- Safety plane location: TODO
