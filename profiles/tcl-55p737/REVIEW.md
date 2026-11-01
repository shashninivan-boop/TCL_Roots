# Owner inventory, TCL 55P737

Android TV 11, firmware V8-R51MT05-LF1V620.021315, Project ID 39433.
Only package names were retained from the owner-provided output; no serials,
MAC addresses, account data or raw device dump are stored here.

Keep on Home, in order: VK Video (`com.vk.tv`), YouTube
(`com.google.android.youtube.tv`), Happ (`com.happproxy`), Kinopoisk (`ru.kinopoisk.tv`).
The installed Happ package name is observed, not verification of its publisher.

`config.json` hides the other inventoried apps from Home, not from Android.
The Settings, network and Inputs controls remain available in the new launcher.
Apps installed later may appear until added to hidden_apps.

`apps-to-disable.txt` contains seven unwanted entertainment apps. Use upstream
disable/restore tools, which record each original state and guard critical packages.
Review the resulting disabled list and test the four required apps after the batch.
Do not reboot until package state has been written (wait at least 15 seconds).

Further audit candidates, NOT yet approved for blind disabling:
com.tcl.bi, com.tcl.logkit, com.tcl.partnercustomizer, com.tcl.waterfall.overseas,
com.tcl.tv.tclhome_passive, com.tcl.esticker, com.tcl.channelplus,
com.tcl.overseasappshow. Read their actual dumpsys package reports first.

Keep TCL settings, TV/input middleware, Bluetooth/pairing, keyboards, networking,
Google Play/Services, package installer, permissions, WebView providers, updater,
setupwraith, accessibility, Chromecast, Miracast, voice assistant and all other
unidentified services unchanged in this pass. Also keep Proton/AdGuard/other VPNs
until the owner confirms that Happ alone provides the required connectivity.

The stock launcher is handled ONLY by upstream build-and-install.ps1, after the new
launcher starts and with its built-in rollback. No manual disable command for Home
or setupwraith is included in the list. Verify the focused activity, the real Home
button, volume, Settings and HDMI; a reported default alone is not enough.

AirPlay is requested for a later stage. No AirPlay app is bundled or installed now.
