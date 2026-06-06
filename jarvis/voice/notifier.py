"""Desktop notifications via notify-send."""

import subprocess


def notify(summary: str, body: str = "", icon: str = "", urgency: str = "normal", transient: bool = True):
    """Send a desktop notification via notify-send.

    Args:
        summary: Notification title.
        body: Notification body text.
        icon: Icon name or path.
        urgency: low, normal, or critical.
        transient: If True, auto-dismiss the notification.
    """
    cmd = ["notify-send"]
    cmd.extend(["--urgency", urgency])
    if transient:
        cmd.extend(["--expire-time", "0"])
    if icon:
        cmd.extend(["--icon", icon])
    cmd.append(summary)
    if body:
        cmd.append(body)

    try:
        subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError:
        # notify-send not available — silently ignore
        pass


def update_notification(id_file: str, summary: str, body: str = ""):
    """Replace an existing notification or send a new one and save its ID.

    Reads the previous notification ID from *id_file* if it exists,
    sends notify-send with --replace-id, and writes the new ID back.
    """
    replace_id = None
    try:
        with open(id_file, "r") as f:
            replace_id = f.read().strip()
    except FileNotFoundError:
        pass

    cmd = ["notify-send", "--print-id"]
    if replace_id:
        cmd.extend(["--replace-id", replace_id])
    cmd.append(summary)
    if body:
        cmd.append(body)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            new_id = result.stdout.strip().splitlines()[-1]
            with open(id_file, "w") as f:
                f.write(new_id)
    except FileNotFoundError:
        pass
