# Jarvis Master Migration

Date: 2026-06-05

## Master Target

`/home/dhairya/Projects/Jarvis/V2`

## Sources Searched

- `/home/dhairya/jarvis`
- `/home/dhairya/jarvis_v2_backup`
- `/home/dhairya/.local/bin/jarvis`
- `/home/dhairya/.config/systemd/user/*jarvis*.service`
- Jarvis-related paths discovered under `/home/dhairya`

## Imported From Old Jarvis

- `automation_hub.py`: OS hardware, Hyprland window, process/app, Git,
  package, media, and system health helpers.
- `speed_ops.py`: lightning audio playback and high-speed command batch helper.
- `file_watcher.py`: notes ingestion watcher.
- `clip_watcher.py`: proactive clipboard insight watcher.
- `launch_gui.py`: fullscreen native webview launcher for the V2 HUD.
- `test_cli.py`: minimal direct agent test CLI.
- Old roadmap and system audit docs archived under `legacy_import/docs/`.
- Old sandbox examples archived under `legacy_import/sandbox_examples/`.
- Old Flask/SocketIO GUI archived under `legacy_import/old_gui/`.

## Master Integrations

- V2 `tools.py` now exposes the old capability surface:
  - `find_and_open_file`
  - `lightning_play`
  - `high_speed_plan`
  - `os_hardware_control`
  - `os_window_control`
  - `os_process_control`
  - `git_ops`
  - `package_ops`
  - `system_health_report`
  - `media_control`
- Runtime sandbox moved from `~/jarvis/sandbox` to `~/.jarvis/sandbox`, so the
  old source tree can be removed safely.
- `~/.local/bin/jarvis` now launches the V2 CLI.
- User services now point to V2:
  - `jarvis.service`
  - `jarvis-telegram.service`
  - `jarvis-daemon.service`
  - `jarvis-voice.service`
  - `jarvis-file.service`
  - `jarvis-clip.service`
  - `jarvis-hud.service`

## Verification

- `python -m compileall -q /home/dhairya/Projects/Jarvis/V2`
- `bash -n /home/dhairya/Projects/Jarvis/V2/setup.sh`
- V2 tool registry import and dispatch test passed.
- `~/.local/bin/jarvis --help` resolves to V2 CLI.
- All Jarvis user services are enabled.

## Old Copies Eligible For Deletion After Approval

- `/home/dhairya/jarvis`
- `/home/dhairya/jarvis_v2_backup`

Do not delete `.jarvis`, `.jarvis_app`, `Pictures/Jarvis`, or active systemd
service files. They are runtime state, virtualenv/dependencies, outputs, and
active control-plane files.
