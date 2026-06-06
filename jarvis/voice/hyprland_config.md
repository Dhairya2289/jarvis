# Hyprland Configuration for JARVIS Voice

Add the following to your `~/.config/hypr/hyprland.conf`:

```ini
# JARVIS Voice keybind
bind = SUPER, J, exec, /usr/bin/python3 -m jarvis.cli --voice

# JARVIS Voice pill window rules (if using window title)
windowrule = float, ^(JARVIS Voice)$
windowrule = size 480 70, ^(JARVIS Voice)$
```

After saving, reload Hyprland with `hyprctl reload` or restart your session.

Press `Super + J` to activate voice command mode anywhere.
