# CleanYourTV reference

Source: https://github.com/Gathin23/cleanyourtv
Revision: `92fdd142566b8c55a5540a96fcdafb889141f644`
License: MIT (included alongside this file).

`adb-closed.py` is copied unchanged from `tools/adb-closed.py` at this revision.
It distinguishes refused connections from timeouts, unreachable devices and
local relays. Use it from the same local network as the television.

Our workflow follows the upstream principles of inspecting the actual device,
recording package state before changes, and closing debugging afterwards.
The Windows kit also packages the upstream launcher (only config.xml configured
for this TV) and original disable/restore/install/theme tools. No add-ons or third-party
device debloat lists are applied. The owner's seven-app list is maintained separately.
Upstream has no exact 55P737 profile at the referenced revision. The nearby
50P735 profile is provisional and is deliberately not used here.
