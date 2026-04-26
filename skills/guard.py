# this skills is mandatory and cannot be disabled on screen
# it is used for monitoring skills usage and make use of skills safe
# for user. Example: if AI tries to send a sms using kdeconnect,
# a full screen alert using /home/gabi/.config/i3/hanauta/src/pyqt/shared/fullscreen_alert.py
# will appear twice to make sure user allows it and the content of the sms message and destination
# user can allow it for the session or for the next 30 minutes without being prompted again.
# Same thing can happens for open/close garage door since it can kill a person passing by,
# it'll  always ask user using /home/gabi/.config/i3/hanauta/src/pyqt/shared/fullscreen_alert.py
# Study other skills from this folder and see what more can this guard skill do