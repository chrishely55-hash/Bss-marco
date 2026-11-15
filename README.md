# BSS Android macro

Runs in Termux on the phone (install Termux, Termux:API from F-Droid). Untested on a real phone: expect tuning.

## Install
    pkg install python android-tools termux-api
    pip install pillow
    termux-wake-lock

Turn on Developer options > Wireless debugging. `python bss.py setup` walks you through pairing.

## Commands (in order)
    python bss.py setup              # learns joystick, backpack bar, Make Honey, tool tap, reset from YOUR taps
    python bss.py check              # shows backpack % so you can verify bar reading
    python bss.py add-field sunflower   # record walking from hive to field, then stay still 6s
    python bss.py add-task dispenser    # record walk + button taps; walk-back and reset happen automatically
    python bss.py schedule dispenser 60 # run that task every 60 min
    python bss.py plan sunflower pine   # field order (add-field appends automatically)
    python bss.py webhook <discord url> # status messages
    python bss.py run --minutes 60

Add `--dry` before the command to print ADB calls without sending them.

## What it does
Reset, walk the recorded route, zigzag the joystick (tapping your tool between drags) until the backpack bar is 95% full, walk back by reversing the route, tap Make Honey until the bar empties. Scheduled tasks run between fields. If Roblox leaves the foreground it relaunches via `roblox://placeId=1537690962` (check the ID, or edit `join` in bss_data.json to a private server link). If the screen stops changing for ~4 checks it resets.

## Limits
- No OCR quest reading and no token chasing by color: quests are recorded walks/taps.
- Taps and joystick can't happen at the same time, so tool taps happen between drags. Your tool must collect on its own while you move.
- Walk-back reverses joystick drags only; record routes as short straight drags, and keep the camera angle fixed.
- Rejoin doesn't detect in-game error popups, only a closed app.
- Roblox rules can restrict automation; use at your own risk and don't leave it unattended.
