# vim: ts=4 sw=4 noexpandtab
"""Stream freecam

Allow freecam usage only for players using STREAM tag.

What this script does is it moves players (camera) who are dead to specific position facing up to the sky.
If player moves from this position he is moved back to same position.

I don't think there is a way to disable freecam only for specific players.
Disabling freecam with sv.allowFreeCam during a match doesn't work too,
it disables freecam also for player who is already freecaming.
There is also no way to disable player's ability to move.

===== Config =====
 # Set how often player's position and state is checked (seconds)
 mm_stream_freecam.sampleRate 0.8

 # How long after the server start script starts to work. There shouldn't be need to change this.
 mm_stream_freecam.initDelay 10

 # Height to which player is moved to when freecaming.
 # Big maps have problem with vehicles disappearing on minimap when player is far away.
 # Maximal height for most problematic 16 size maps:
 # - road rage - 400 - north-east jeep (by garage) disappears first
 # - zatar - 390
 # - dragon - 440 - US heli disappears first
 mm_stream_freecam.height 390.0

 # Players with this prefix are not moved by the script.
 mm_stream_freecam.streamerPrefix 'STREAM'

===== Rcon commands =====
 # You have to log in before using this commands.
 # Invocation:
 # rcon stream_freecam <command> <parameter>

 # Enable and disable this module
 enable <0/1>

 # Set height, see mm_sample.height description above
 height <int>

===== History =====
 v0.1 - 08/02/2022:
 Initial version

 v1.0 - 19/03/2022:
 Public release
 Fixed problem with uav not visible on start
 Fixed problem with vehicles disheartening on minimap

Author: Michal 'Breiker' Breiter
"""

import bf2
import host
import math
import mm_utils

# Set the version of your module here
__version__ = 1.0

# Set the required module versions here
__required_modules__ = {
    'modmanager': 1.6
}

# Does this module support reload ( are all its reference closed on shutdown? )
__supports_reload__ = True

# Sets which games this module supports
__supported_games__ = {
    'bf2': True,
    'bf2142': True
}

# Set the description of your module here
__description__ = "StreamFreecam v%s" % __version__

# Add all your configuration options here
configDefaults = {
    'sampleRate': 0.8,
    'initDelay': 10,
    'height': 390.0,
    'streamerPrefix': 'STREAM',
}


class StreamFreecam(object):

    def __init__(self, modManager):
        # ModManager reference
        self.mm = modManager

        # Internal shutdown state
        self.__state = 0

        # Add any static initialisation here.
        # Note: Handler registration should not be done here
        # but instead in the init() method

        # Your rcon commands go here:
        self.__cmds = {
            'enable': {'method': self.cmdEnable, 'level': 10},
            'height': {'method': self.cmdHeight, 'level': 10}
        }

        # y
        self.height = None
        # only [x, z]
        self.middle_of_the_map = None
        self.streamer_prefix = None
        # is server setting for allowFreeCam set to 1
        self.freecam_enabled = None
        # allow disabling module via rcon
        self.module_enabled = True

    def cmdExec(self, ctx, cmd):
        return mm_utils.exec_subcmd(self.mm, self.__cmds, ctx, cmd)

    def cmdEnable(self, ctx, cmd):
        parts = cmd.split()
        l = len(parts)
        if 0 == l:
            ctx.write('Error: no argument (0 or 1) specified\n')
            return 0
        try:
            self.module_enabled = int(parts[0])
            ctx.write('%s set to enabled? %s\n' % (__description__, self.module_enabled))
        except:
            ctx.write("Error: Enable with '%s'\n" % parts[0])

    def cmdHeight(self, ctx, cmd):
        parts = cmd.split()
        l = len(parts)
        if 0 == l:
            ctx.write('Error: no argument (int) specified\n')
            return 0
        try:
            self.height = float(parts[0])
            ctx.write('%s height set to: %s\n' % (__description__, self.height))
        except:
            ctx.write("Error: Height with '%s'\n" % parts[0])

    def moveDeadPlayer(self, player):
        """Move dead player high.
        """
        if not player or player.isAlive():
            # self.mm.info('Error: Player is currently alive')
            return 0
        try:
            player_name = player.getName()
        except:
            self.mm.error("Failed to check player name", True)

        if player_name.startswith(self.streamer_prefix):
            # self.mm.info("Ignoring streamer player %s" % player_name)
            return 0

        try:
            veh = player.getVehicle()
            pos = veh.getPosition()
            rot = veh.getRotation()

            # self.mm.info('rel checking last pos: %s rot: %s' % (pos, rot))
            new_pos_tuple = (self.middle_of_the_map[0], self.height, self.middle_of_the_map[1])
            new_rot_tuple = (0.0, -90.0, 0.0)
            if pos == new_pos_tuple and rot == new_rot_tuple:
                # self.mm.info('same pos and rot, ignoring')
                return 0
            veh.setRotation(new_rot_tuple)
            veh.setPosition(new_pos_tuple)
            # self.mm.info("Tried to move player'%s' isManDown %s" % (player_name, player.isManDown()))
        except Exception, e:
            self.mm.error('Failed to move player', True)

    def checkPlayers(self, params=None):
        """Check players for ping violations and update advanced player info"""
        try:
            if 1 != self.__state:
                return 0
            if not self.mm.gamePlaying:
                # not playing atm, ignore
                return
            if not self.module_enabled or not self.freecam_enabled:
                # self.mm.info("Plugin enabled %s, freecam enabled %s" % (self.plugin_enabled, self.freecam_enabled))
                return

            for player in bf2.playerManager.getPlayers():
                try:
                    if not player.isConnected():
                        # ignore players still connecting
                        continue

                    if not player or player.isAlive():
                        # ignore alive players
                        continue

                    self.moveDeadPlayer(player)
                except:
                    try:
                        player_name = player.getName()
                    except:
                        player_name = 'unknown'
                    self.mm.error("Failed to check player '%s'" % player_name, True)
        except:
            self.mm.error("Got exception", True)

    def onGameStatusChanged(self, status):
        """Update settings which depend on map and server settings."""
        if 1 != self.__state:
            return
        self.mm.info('%s onGameStatusChanged %s' % (__description__, status))
        try:
            if not bf2.GameStatus.Playing == status:
                self.mm.info("Not Playing, ignoring %s" % status)
                return

            # check if freecam is enabled only on restart
            # host.ss_getParam('allowFreeCam') gives 'unknown serversetting'
            self.freecam_enabled = host.rcon_invoke('sv.getAllowFreeCam') == "1\n"
            self.mm.info("Freecam is enabled? %s setting '%s'" % (self.freecam_enabled, host.rcon_invoke('sv.getAllowFreeCam')))

            # No point in additional processing
            if not self.freecam_enabled:
                return

            # Make bounding box from all points which are not neutral.
            # We are trying to calculate 'fair' middle of the map to move players camera to.
            control_points = bf2.objectManager.getObjectsOfType('dice.hfe.world.ObjectTemplate.ControlPoint')
            min_pos = [float('inf'), float('inf')]
            max_pos = [-float('inf'), -float('inf')]
            for cp in control_points:
                if cp.cp_getParam("team") == 0:
                    # self.mm.info("Ignoring neutral cp %s" % cp.cp_getParam("team"))
                    # ignore neutral flags
                    continue
                (x, y, z) = cp.getPosition()
                # printing tuple crashes whole function
                # self.mm.info("Checking cp %s,%s,%s" % (x, y, z))
                min_pos[0] = min(x, min_pos[0])
                min_pos[1] = min(z, min_pos[1])
                max_pos[0] = max(x, max_pos[0])
                max_pos[1] = max(z, max_pos[1])
            # We have to round the result, player may be moved not precisely to this position, there is probably
            # some rounding in setPosition. If we don't do this, when we check if player moved we get different
            # position even if player didn't move.
            self.middle_of_the_map = [math.floor((min_pos[0] + max_pos[0]) / 2.0), math.floor((min_pos[1] + max_pos[1]) / 2.0)]
            self.mm.info("Middle of the map %s" % self.middle_of_the_map)
        except:
            self.mm.error("% Got exception" % __description__, True)

    def loadOftenUsedConfigVariables(self):
        self.streamer_prefix = self.__config['streamerPrefix']
        self.height = self.__config['height']

    def init(self):
        """Provides default initialisation."""

        # Load the configuration
        self.__config = self.mm.getModuleConfig(configDefaults)
        self.loadOftenUsedConfigVariables()

        # Register your game handlers and provide any
        # other dynamic initialisation here

        # onDeath handler is not useful here. When player dies he didn't yet enter freecam state.

        # Register our base handlers
        host.registerGameStatusHandler(self.onGameStatusChanged)

        # Register our rcon command handlers
        self.mm.registerRconCmdHandler('stream_freecam', {'method': self.cmdExec, 'subcmds': self.__cmds, 'level': 1})

        # set up our times
        self.__checkTimer = bf2.Timer(self.checkPlayers, self.__config['initDelay'], 1)
        self.__checkTimer.setRecurring(self.__config['sampleRate'])

        # Update to the running state
        self.__state = 1

    def shutdown(self):
        """Shutdown and stop processing."""

        # destroy our timers
        self.__checkTimer.destroy()
        self.__checkTimer = None

        # Unregister game handlers and do any other
        # other actions to ensure your module no longer affects
        # the game in anyway
        self.mm.unregisterRconCmdHandler('stream_freecam')

        # Unregister our game handlers
        host.unregisterGameStatusHandler(self.onGameStatusChanged)

        # Flag as shutdown as there is currently way to:
        # host.unregisterHandler
        self.__state = 2

    def update(self):
        """Process and update.
        Note: This is called VERY often processing in here should
        be kept to an absolute minimum.
        """
        pass


def mm_load(modManager):
    """Creates and returns your object."""
    return StreamFreecam(modManager)
