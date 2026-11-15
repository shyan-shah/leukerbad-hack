#!/bin/bash
# Start Flexiv Elements Studio (Linux build) under WSL with WSLg. PC-side app only.
# Usage inside WSL:  bash run_studio.sh [studio folder]      (default ~/flexiv/studio-3.9.3)
# From Windows:      wsl -d Ubuntu-22.04 -u shyan -- bash -lc "~/flexiv/studio-3.9.3/run_studio.sh"
# Same settings as Flexiv's own run_FlexivElements.sh, plus the xcb platform, without storing a sudo password.
# In the window: REFRESH, then Connect. Decline every "update robot" prompt.
cd "${1:-$HOME/flexiv/studio-3.9.3}" || exit 1
pkill -9 FlexivElements 2>/dev/null
unset http_proxy https_proxy
export LD_LIBRARY_PATH="$PWD/lib:$LD_LIBRARY_PATH"
export QT_QPA_PLATFORM_PLUGIN_PATH="$PWD/plugins"
export QT_QPA_PLATFORM=xcb
export QTWEBENGINE_DISABLE_SANDBOX=1
export DISPLAY="${DISPLAY:-:0}"
exec ./FlexivElementsStudio -p ubuntu_pc
