# vim: ts=4 sw=4 noexpandtab
"""Warmup tdm mode

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
import mm_utils

# Set the version of your module here
__version__ = 0.7

# Set the required module versions here
__required_modules__ = {
    'modmanager': 1.6
}

# Does this module support reload ( are all its reference closed on shutdown? )
__supports_reload__ = True

# Sets which games this module supports
__supported_games__ = {
    'bf2': True,
}

# Set the description of your module here
__description__ = "Warmup v%s" % __version__

# Add all your configuration options here
configDefaults = {
    'sampleRate': 20,
    'initDelay': 10,
    # assume every setting is int
    'changedVariables': {
        'sv.spawnTime': 1,
        'sv.soldierFriendlyFire': 2,
        'sv.manDownTime': 0,
        'sv.timeBeforeRestartMap': 5,
        'sv.startDelay': 5,
        'sv.endDelay': 3,
        'sv.endOfRoundDelay': 4,
        'sv.ticketRatio': 800,
        'sv.timeLimit': 3600,
    },
    'streamerPrefix': 'STREAM',
}

# TODO
# - fix team assignment - comment in onPlayerChangeTeams
# - add more pos
# - block flags
# - fast live after live round?

class Warmup(object):
    class PlayerState(object):
        NOT_READY = 0
        READY = 1
        STREAM = 2

        strings = [
            "NOT_READY",
            "READY",
            "STREAM"
        ]

        def __init__(self, team, name):
            self.team = team
            self.name = name
            self.ready = self.NOT_READY
            self.times_spawned = 0

        # Python support here is challenging
        def string(ps):
            return Warmup.PlayerState.strings[ps]

        string = staticmethod(string)

        def resetAfterRound(self):
            self.times_spawned = 0

    class RoundState(object):
        UNKNOWN = 0
        NEXT_WARMUP = 1
        WARMUP = 2
        NEXT_LIVE = 3
        PREVIOUS_LIVE = 4
        LIVE = 5

        strings = [
            "UNKNOWN",
            "NEXT_WARMUP",
            "WARMUP",
            "NEXT_LIVE",
            "PREVIOUS_LIVE",
            "LIVE",
        ]

        # Python support here is challenging
        def string(ps):
            return Warmup.RoundState.strings[ps]

        string = staticmethod(string)

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
        }

        self.round_state = Warmup.RoundState.UNKNOWN

        self.stored_settings = None
        # state of players
        self.player_state = {}
        # allow disabling module via rcon
        self.module_enabled = True

        self.streamer_prefix = None

        self.team1_name = 'US'
        self.team2_name = 'MEC'

        self.fake_restarts = 0

        self.current_map = ''
        self.current_spawn = 0
        self.spawns = {
            'strike_at_karkand': [
                ((-186.0, 156.0, 44.0), (162.0, 0.0, 0.0)),  # square to hotel corridor facing south
                ((-168.0, 156.0, 35.0), (-175.0, 0.0, 0.0)),  # square to hotel east main arches
                ((-139.0, 156.0, 28.0), (-118.0, 0.0, 0.0)),  # east east, hotel north spawn height
                ((-140.0, 156.0, 1.0), (-68.0, 0.0, 0.0)),  # east east, south spawn height
                ((-144.0, 156.0, -18.0), (-112.0, 0.0, 0.0)),  # east east, first corridor from us hill
                ((-178.0, 156.0, -26.0), (-94.0, 0.0, 0.0)),  # chicken coup
                ((-178.0, 156.0, -12.0), (-91.0, 0.0, 0.0)),  # box by south roof
                ((-211.0, 156.0, -37.0), (-3.0, 0.0, 0.0)),  # barricates south of burning car
                ((-226.0, 156.0, -21.0), (41.0, 0.0, 0.0)),  # burning car
                ((-229.0, 156.0, -7.0), (-86.0, 0.0, 0.0)),  # back of lmg spawn hotel
                ((-249.0, 156.0, 17.0), (45.0, 0.0, 0.0)),  # fence by arch hotel
                ((-253.0, 156.0, 34.0), (104.0, 0.0, 0.0)),  # tree north west hotel by telephone booth
                ((-225.0, 156.0, 65.0), (121.0, 0.0, 0.0)),  # south of north hotel phone booth
            ]
        }

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

    def storeSettings(self):
        self.mm.info('[WARMUP] storeSettings')
        self.stored_settings = {}
        try:
            # TODO don't use configDefaults, use self.__config
            self.mm.info('[WARMUP] storeSettings try')
            for (setting, val) in configDefaults['changedVariables'].iteritems():
                self.mm.info('[WARMUP] storeSettings: setting %s val %s' % (setting, val))
                self.stored_settings[setting] = int(host.rcon_invoke(setting))
                self.mm.info('[WARMUP] storeSettings: after setting %s val %s' % (setting, val))
        except:
            self.mm.error("% Got exception" % __description__, True)
        self.mm.info('[WARMUP] storeSettings after')

    def changeSettings(self):
        self.mm.info('[WARMUP] changeSettings')
        for name, val in configDefaults['changedVariables'].iteritems():
            host.rcon_invoke('%s %s' % (name, val))

    def restoreSettings(self):
        self.mm.info('[WARMUP] restoreSettings')
        # TODO keep if different
        for name, val in self.stored_settings.iteritems():
            self.mm.info('[WARMUP] restoreSettings (%s : %s)' % (name, val))
            host.rcon_invoke('%s %s' % (name, val))

    def restartMap(self):
        self.mm.info('[WARMUP] restartMap')
        host.rcon_invoke('admin.restartMap')

    def switchToWarmup(self):
        self.mm.info('[WARMUP] switchToWarmup')
        self.storeSettings()
        self.changeSettings()
        self.restartMap()
        self.round_state = Warmup.RoundState.NEXT_WARMUP

    def switchToLive(self):
        self.mm.info('[WARMUP] switchToLive')
        self.restoreSettings()
        self.restartMap()
        self.round_state = Warmup.RoundState.NEXT_LIVE

    def updatePlayersTeams(self):
        players = bf2.playerManager.getPlayers()
        for player in players:
            self.mm.info('[WARMUP] updatePlayerTeams P(%s) T(%s)' % (player.index, player.getTeam()))
            self.player_state[player.index].team = player.getTeam()

    def fixPlayerTeam(self, player, lazy=True):
        if lazy and self.player_state[player.index].times_spawned > 1:
            return
        team = player.getTeam()
        if self.player_state[player.index].team != team:
            self.player_state[player.index].team = team
            self.checkState()

    def resetStatsAfterRound(self, reset_ready=False):
        for _, state in self.player_state.iteritems():
            state.resetAfterRound()
            if reset_ready and state.ready == Warmup.PlayerState.READY:
                state.ready = Warmup.PlayerState.NOT_READY


    def checkState(self):
        """Check if we have enough players to change state"""

        if self.round_state != Warmup.RoundState.WARMUP:
            return
        team1_ready = 0
        team1_not_ready = 0

        team2_ready = 0
        team2_not_ready = 0

        for index, state in self.player_state.iteritems():
            if state.ready == Warmup.PlayerState.STREAM:
                continue
            if state.team == 1:
                if state.ready == Warmup.PlayerState.READY:
                    team1_ready += 1
                else:
                    team1_not_ready += 1
            else:
                if state.ready == Warmup.PlayerState.READY:
                    team2_ready += 1
                else:
                    team2_not_ready += 1

        # some not ready
        if team1_not_ready or team2_not_ready:
            return

        # ignore too small teams
        # TODO Change back to higher number?
        if team1_ready + team2_ready < 2:
            return

        # Should we ignore not even teams? Try STREAM for now
        if team1_ready != team2_ready:
            return
        self.switchToLive()

    def printState(self, params=None):
        """Just inform players about state"""
        if 1 != self.__state:
            return 0
        if not self.mm.gamePlaying:
            # not playing atm, ignore
            return
        if not self.module_enabled:
            return
        # TODO change to only display on WARMUP state
        if self.round_state == Warmup.RoundState.LIVE:
            return
        try:
            format_team = "Team %s: R(%s) NR(%s)"
            format_game = "Game State: %s STREAM(%s) Commands: [/ready, /notready, /disable]"
            # I could use two dicts here, but I feel that that may be slower
            team1_nr = ""
            team1_r = ""
            team2_nr = ""
            team2_r = ""
            stream = ""
            for index, state in self.player_state.iteritems():
                if state.ready == Warmup.PlayerState.STREAM:
                    stream += state.name + ', '
                elif state.team == 1:
                    if state.ready == Warmup.PlayerState.READY:
                        team1_r += state.name + ', '
                    else:
                        team1_nr += state.name + ', '
                else:
                    if state.ready == Warmup.PlayerState.READY:
                        team2_r += state.name + ', '
                    else:
                        team2_nr += state.name + ', '

            mm_utils.msg_server(format_team % (self.team1_name, team1_r, team1_nr))
            mm_utils.msg_server(format_team % (self.team2_name, team2_r, team2_nr))
            mm_utils.msg_server(format_game % (Warmup.RoundState.string(self.round_state), stream))
        except:
            self.mm.error("Got exception", True)

    def onPlayerConnect(self, p):
        """Initialize player on connect."""
        if 1 != self.__state:
            return

        self.mm.info('on player connect (%s)' % p.index)
        player_team = p.getTeam()
        player_index = p.index
        try:
            player_name = p.getName()
        except:
            player_name = 'UnknownPlayer'

        self.mm.info('player (%s) \'%s\' connected - team %s' % (player_index, player_name, player_team))

        self.player_state[player_index] = Warmup.PlayerState(player_team, player_name)

        if player_name.startswith(self.streamer_prefix):
            self.player_state[player_index].ready = Warmup.PlayerState.STREAM

    def onPlayerChangeTeams(self, p, humanHasSpawned):
        """Switch team. Note that this callback is not called if player got switched with switchTeam."""
        if 1 != self.__state:
            return

        self.mm.info('player \'%s\' changed teams to: %s' % (p.index, p.getTeam()))
        self.player_state[p.index].team = p.getTeam()
        self.checkState()

    # When players disconnect, remove them from the auth map if they were
    # authenticated so that the next user with the same id doesn't get rcon
    # access.
    def onPlayerDisconnect(self, player):
        if 1 != self.__state:
            return 0
        if self.player_state.has_key(player.index):
            del self.player_state[player.index]
            # maybe we have enough now
            self.checkState()

    def dumpPos(self, playerid, comment):
        try:
            player = bf2.playerManager.getPlayerByIndex(playerid)
            veh = player.getVehicle()
            pos = veh.getPosition()
            rot = veh.getRotation()

            message = 'DUMP pos: \'((%s.0, %s.0, %s.0), (%s.0, %s, %s)), # %s\'' % \
                      (int(pos[0]), int(pos[1]), int(pos[2]), int(rot[0]), rot[1], rot[2], comment)
            self.mm.info(message)
            return message
        except Exception, e:
            self.mm.error('Failed to get player pos', True)

    def onChatMessage(self, playerid, text, channel, flags):
        """Called whenever a player issues a chat string."""
        if 1 != self.__state:
            return 0

        # server message - channel 'ServerMessage'
        if playerid < 0:
            return
        self.mm.info('player \'%s\' message \'%s\' channel: \'%s\' flags:\'%s\'' % (playerid, text, channel, flags))
        pure_text = mm_utils.MsgChannels.named[channel].stripPrefix(text).lower()
        if pure_text[0] != '/':
            return
        if pure_text == "/ready" or pure_text == '/r':
            self.player_state[playerid].ready = Warmup.PlayerState.READY
            self.checkState()
            self.printState()
        elif pure_text == "/notready" or pure_text == '/nr':
            self.player_state[playerid].ready = Warmup.PlayerState.NOT_READY
            self.checkState()
            self.printState()
        elif pure_text == "/stream":
            self.player_state[playerid].ready = Warmup.PlayerState.STREAM
            self.checkState()
            self.printState()
        elif pure_text == '/mapname':
            self.mm.info('DUMP mapname: \'%s\'' % host.sgl_getMapName())
        elif pure_text.startswith('/pos'):
            comment = pure_text.replace('/pos', '', 1).strip()
            mm_utils.msg_server(self.dumpPos(playerid, comment))
        elif pure_text == '/disable':
            if self.module_enabled:
                self.switchToLive()
                self.module_enabled = False
        elif pure_text == '/help':
            self.mm.info("%s commands: [/ready; /r; /notready; /nr; /stream]" % __description__)
            self.mm.info("%s test commands: [/pos <description> - report position to add; /disable - disable module]" % __description__)
        elif pure_text == '/set_pos':
            if self.module_enabled and self.round_state == Warmup.RoundState.WARMUP:
                self.changePos(playerid)

    #def onPlayerChangeWeapon(self, player, oldWeapon, newWeapon):
        # # only on spawn changes from none to something
        # if oldWeapon:
        #     return

    def onPlayerSpawn(self, player, soldier):
        """Move player."""
        if 1 != self.__state:
            return 0

        self.mm.info('[WARMUP] onPlayerSpawn')

        if self.round_state != Warmup.RoundState.WARMUP or not self.module_enabled:
            return 0

        # not sure if it's needed
        # player is not player.isAlive() when this function is called
        if not player:
            self.mm.info('Error: Player spawned but is None')
            return 0

        self.player_state[player.index].times_spawned += 1
        # see comments in onPlayerChangeTeams
        self.fixPlayerTeam(player)

        try:
            veh = player.getVehicle()
            # determine position to spawn
            if self.spawns.has_key(self.current_map):
                self.current_spawn = (self.current_spawn + 1) % len(self.spawns[self.current_map])
                (new_pos_tuple, new_rot_tuple) = self.spawns[self.current_map][self.current_spawn]
                new_pos_tuple = (new_pos_tuple[0], new_pos_tuple[1], new_pos_tuple[2])
                new_rot_tuple = (new_rot_tuple[2], new_rot_tuple[1], -new_rot_tuple[0])
                # new_rot_tuple = (30.0, 90.0, 0.0)
            else:
                pos = veh.getPosition()
                rot = veh.getRotation()
                new_pos_tuple = (pos[0], pos[1] + 3, pos[2])
                new_rot_tuple = (0.0, -90.0, 0.0)
                self.mm.info('rel checking last pos: %s rot: %s' % (pos, rot))

            veh.setPosition(new_pos_tuple)
            veh.setRotation(new_rot_tuple)
            self.mm.info("Tried to move player'%s' isManDown %s" % (player.index, player.isManDown()))
        except Exception, e:
            self.mm.error('Failed to move player', True)

    def changePos(self, playerid):
        try:
            player = bf2.playerManager.getPlayerByIndex(playerid)
            veh = player.getVehicle()
            pos = veh.getRotation()
            rot = veh.getRotation()
            veh.setRotation((30.0, 90.0, 10.0))

            message = 'DUMP pos: \'((%s.0, %s.0, %s.0), (%s.0, %s, %s)), # %s\'' % \
                      (int(pos[0]), int(pos[1]), int(pos[2]), int(rot[0]), rot[1], rot[2], '')
            self.mm.info(message)
            return message
        except Exception, e:
            self.mm.error('Failed to get player pos', True)


    def onGameStatusChanged(self, status):
        """Update settings which depend on map and server settings."""
        if 1 != self.__state:
            return
        self.mm.info('%s onGameStatusChanged %s state: %s started: %s fake_restarts: %s' %
                     (__description__, mm_utils.status_name(status), Warmup.RoundState.string(self.round_state),
                      self.mm.roundStarted, self.fake_restarts))
        try:
            if bf2.GameStatus.PreGame == self.mm.lastGameStatus and bf2.GameStatus.Playing == status:
                if self.fake_restarts >= 2:
                    self.fake_restarts = 1
                else:
                    self.fake_restarts += 1

            if not bf2.GameStatus.Playing == status:
                self.mm.info("Not Playing, ignoring %s" % status)
                return

            if not self.module_enabled:
                return
            if not self.mm.roundStarted:
                self.mm.info('Round not started')
                return
            # mm.roundStarted doesn't work with map restart, there is no EndGame state which resets restart count
            if self.fake_restarts != 2:
                self.mm.info('Waiting for fake restarts')
                return

            if self.round_state == Warmup.RoundState.NEXT_WARMUP:
                self.mm.info('[WARMUP] NEXT_WARMUP -> WARMUP')
                mm_utils.msg_server("WARMUP")
                self.round_state = Warmup.RoundState.WARMUP
            elif self.round_state == Warmup.RoundState.LIVE:
                self.mm.info('[WARMUP] LIVE -> WARMUP')
                self.switchToWarmup()
            elif self.round_state == Warmup.RoundState.NEXT_LIVE:
                self.mm.info('[WARMUP] NEXT_LIVE -> LIVE')
                mm_utils.msg_server("LIVE GL&HF")
                self.round_state = Warmup.RoundState.LIVE
            elif self.round_state == Warmup.RoundState.UNKNOWN:
                self.mm.info('[WARMUP] UNKNOWN -> WARMUP')
                self.switchToWarmup()

            # update team names
            map_now = host.sgl_getMapName()
            if self.current_map != map_now:
                self.team1_name = host.sgl_getParam('teamName', 1, 0)
                self.team2_name = host.sgl_getParam('teamName', 2, 0)
            self.current_map = map_now

            # refresh stats
            self.resetStatsAfterRound(reset_ready=(self.round_state == Warmup.RoundState.LIVE))

            # update teams after connect
            # TODO make it better
            self.updatePlayersTeams()
        except:
            self.mm.error("% Got exception" % __description__, True)

    def loadOftenUsedConfigVariables(self):
        self.streamer_prefix = self.__config['streamerPrefix']
        return

    def assumeWeDontTestVehicles(self):
        no_vehicles = int(host.rcon_invoke('sv.noVehicles'))
        if no_vehicles == 0:
            self.module_enabled = False
        self.mm.info("NoVehicles? %s Enabled %s" % (no_vehicles, self.module_enabled))
        return self.module_enabled

    def init(self):
        """Provides default initialisation."""

        # Load the configuration
        self.__config = self.mm.getModuleConfig(configDefaults)
        self.loadOftenUsedConfigVariables()
        if not self.assumeWeDontTestVehicles():
            return

        # Register your game handlers and provide any
        # other dynamic initialisation here

        # Register our game handlers
        if 0 == self.__state:
            host.registerHandler('PlayerConnect', self.onPlayerConnect, 1)
            host.registerHandler('PlayerChangeTeams', self.onPlayerChangeTeams, 1)
            host.registerHandler('PlayerDisconnect', self.onPlayerDisconnect, 1)
            host.registerHandler('PlayerSpawn', self.onPlayerSpawn, 1)
            host.registerHandler('ChatMessage', self.onChatMessage, 1)
            # host.registerHandler('PlayerChangeWeapon', self.onPlayerChangeWeapon)

        # Register our base handlers
        host.registerGameStatusHandler(self.onGameStatusChanged)

        # Register our rcon command handlers
        self.mm.registerRconCmdHandler('warmup', {'method': self.cmdExec, 'subcmds': self.__cmds, 'level': 1})

        # set up our times
        self.__checkTimer = bf2.Timer(self.printState, self.__config['initDelay'], 1)
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
        self.mm.unregisterRconCmdHandler('warmup')

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
    return Warmup(modManager)
