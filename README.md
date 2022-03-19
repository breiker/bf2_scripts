##Stream freecam
File: `admin/modules/mm_stream_freecam.py`

Battlefield 2 doesn't have full spectator mode. You can only spectate players using third-person view or using freecam.
Freecam is used most often by commentators for streams.
Enabling freecam only for selected players is not possible. That's why freecam can be abused to see position of enemy players when waiting to spawn.

This module moves players who are dead to position high in the sky, looking up.
Player can still try to move camera, but he is moved frequently to same position. This makes it almost impossible to see something useful.

Players who have tag `STREAM` can freecam freely. This way other players see who can freecam and who can't.

For implementation details, config and rcon commands see description on top of `mm_stream_freecam.py`.
### Installation

Requirements:
- `modmanager`

If you have BF2CC running on your server you don't have to do anything, you probably have modmanager already installed.
You can find link to modmanager by searching for `modmanager-v1.9.zip`.
You don't need to enable/load other modules in modmanager if you don't need them (see `modmanager.con`).

Put `admin/modules/mm_stream_freecam.py` file inside `admin/modules` folder on your server.\
In `mods/bf2/settings/modmanager.con` find section `Modules` and add line:
```
modmanager.loadModule "mm_stream_freecam"
```
That's all. Module is only doing something when allowFreeCam is enabled on the server.

In `modmanager.con` you can also change settings e.g.:
```
mm_stream_freecam.height 500.0
```
For more settings see description on top of `mm_stream_freecam.py`.