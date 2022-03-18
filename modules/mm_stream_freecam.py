# vim: ts=4 sw=4 noexpandtab
"""Stream freecam

Allow freecam usage only for players using STREAM tag.

===== Config =====
 # Sets option 1
 mm_sample.myOption1 1

 # Sets option 2
 mm_sample.myOption2 "hello there"

===== History =====
 v0.1 - 08/02/2022:
 Initial version

Author: Michal Breiter
"""

import bf2
import host
import mm_utils

# Set the version of your module here
__version__ = 0.1

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
    'sampleRate': 2,
    'initDelay': 10,
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
            'enable': {'method': self.cmdEnable, 'level': 10}
        }

    def cmdExec(self, ctx, cmd):
        """Execute a MyModule sub command."""

        # Note: The Python doc above is used for help / description
        # messages in rcon if not overriden
        return mm_utils.exec_subcmd(self.mm, self.__cmds, ctx, cmd)

    def cmdEnable(self, ctx, cmd):
        """Does XYZ.
        Details about this function
        """
        # Note: The Python doc above is used for help / description
        # messages in rcon if not overriden
        self.mm.debug(2, "Running cmdSample '%s'" % cmd)
        ctx.write("Your arguments where '%s'" % cmd)
        return 1

    def onPlayerSpawn(self, player, soldier):
        """Do something when a player spawns."""
        if 1 != self.__state:
            return 0

    def onPlayerDeath(self, p, vehicle):
        """Move him instantly, don't know if it works any time."""
        if 1 != self.__state:
            return

        if p == None:
            return

        if self.mm.isBattleField2142():
            # bf2142 specific
            if not p.isValid() or p.isAutoController():
                return
        else:
            # bf2 specific
            if (host.ss_getParam('gameMode') == "gpm_coop") and p.isAIPlayer():
                return
        self.mm.error("Checking player death", True)

        self.cmdFling(p, [0.0, 1000.0, 0.0], False)


    def moveDeadPlayer(self, player, new_pos, relative):
        """fling a player high.

        cmd = playerid height

        Taken from mm_bf2cc.py.
        """

        if not player or player.isAlive():
            self.mm.info('Error: Player is currently alive')
            return 0
        try:
            player_name = player.getName()
        except:
            self.mm.error("Failed to check player name", True)

        if player_name.startswith(self.__config['streamerPrefix']):
            # self.mm.info("Ignoring streamer player %s" % player_name)
            return 0

        try:
            veh = player.getVehicle()
            pos = veh.getPosition()

            if relative:
                veh.setPosition(tuple([pos[0] + new_pos[0], pos[1] + new_pos[1], pos[2] + new_pos[2]]))
            else:
                new_pos_tuple = tuple(new_pos)
                # self.mm.info('checking last pos %s' % str(pos))
                if pos == new_pos_tuple:
                    # self.mm.info('same pos, ignoring')
                    return 0
                veh.setPosition(new_pos_tuple)
            # self.mm.info("Tried to move player'%s' isManDown %s" % (player_name, player.isManDown()))
        except Exception, e:
            self.mm.error('Failed to move player', True)

    def checkPlayers(self, params=None):
        """Check players for ping violations and update advanced player info"""
        try:
            if not self.mm.gamePlaying:
                # not playing atm ignore
                return

            for player in bf2.playerManager.getPlayers():
                try:
                    if not player.isConnected():
                        # ignore players still connecting
                        continue

                    if not player or player.isAlive():
                        # ignore alive players
                        continue

                    self.moveDeadPlayer(player, [0.0, 1000.0, 0.0], False)
                except:
                    try:
                        player_name = player.getName()
                    except:
                        player_name = 'unknown'
                    self.mm.error( "Failed to check player '%s'" % player_name, True )
        except:
            self.mm.error( "Ooops :(", True )

    def init(self):
        """Provides default initialisation."""

        # Load the configuration
        self.__config = self.mm.getModuleConfig(configDefaults)

        # Register your game handlers and provide any
        # other dynamic initialisation here

        if 0 == self.__state:
            # Register your host handlers here
            host.registerHandler('PlayerSpawn', self.onPlayerSpawn, 1)
            # host.registerHandler('PlayerDeath', self.onPlayerDeath, 1)

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
