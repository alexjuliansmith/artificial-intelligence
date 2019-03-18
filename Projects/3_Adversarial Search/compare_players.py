import textwrap
from timeit import default_timer as timer

from isolation.isolation import Isolation
from isolation import fork_get_action, Empty, Status, ERR_INFO, StopSearch
from my_custom_player import *
from my_custom_player import IterativeDeepeningPlayer as ID
from sample_players import RandomPlayer

import queue

class MyTimedQueue:

    def __init__(self, player, time_limit):
        self.player = player
        player.queue = self
        self.stop_time = timer() + time_limit / 1000
        self.item = None

    def put(self, item):
        #print("received {} from {}".format(item, self.player))
        if timer() > self.stop_time:
            #print("rejecting due to timeout")
            raise StopSearch
        self.item = item


def summarise_statistics(players):
    summary = {}
    from my_custom_player import INSTRUMENTATION_ON
    if INSTRUMENTATION_ON:
        for player in players:
            id, con = player.player_id, player.context
            sid = {}
            summary[id] = sid
            sid["type"] = type(player)
            sid["moves"] = len(con[ID.METRIC_BRANCHING_FACTOR])
            if sid["moves"]:
                sid["first move ply"] = min(con[ID.METRIC_DEPTH])
                sid["final move ply"] = max(con[ID.METRIC_DEPTH])

                sid["max depth"] = max( (con[ID.METRIC_DEPTH][ply], ply) for ply in con[ID.METRIC_DEPTH])
                sid["mean depth"] = sum(con[ID.METRIC_DEPTH].values()) / len(con[ID.METRIC_DEPTH])

                sid["max nodes searched"] = max( (con[ID.METRIC_NODES_SEARCHED][ply], ply) for ply in con[ID.METRIC_NODES_SEARCHED])
                sid["mean nodes searched"] = sum(con[ID.METRIC_NODES_SEARCHED].values()) / len(con[ID.METRIC_NODES_SEARCHED])
                sid["total nodes searched"] = sum(con[ID.METRIC_NODES_SEARCHED].values())

                sid["mean Branching Factor"] = sum(con[ID.METRIC_BRANCHING_FACTOR].values()) / len(con[ID.METRIC_BRANCHING_FACTOR])
                sid["max Branching Factor"] = max( (con[ID.METRIC_BRANCHING_FACTOR][ply], ply) for ply in con[ID.METRIC_BRANCHING_FACTOR])

    return summary

stats_to_combine = [ID.METRIC_DEPTH,
                    ID.METRIC_NODES_SEARCHED,
                    ID.METRIC_BRANCHING_FACTOR]

def make_combined_statistics():
    return {
        key: defaultdict(list) for key in stats_to_combine
    }

def add_combined_stats(player, combined_stats):
    for key in stats_to_combine:
        stat = player.context[key]
        for ply, value in stat.items():
            combined_stats[key][ply].append(value)

mm = ID_MinimaxPlayer(0)
ab = AlphaBetaPlayer(0)
cust = CustomPlayer(0)



comparees = [mm, ab, cust]
buckets = [make_combined_statistics() for _ in range(len(comparees))]

num_matches = 3
time_limit = 150


for i in range(num_matches):
    initial_state = game = Isolation()
    game_history = []
    while not game.terminal_test():
        for player in comparees:
            player.player_id = game.player()
            q = MyTimedQueue(player, time_limit)
            try:
                player.get_action(game)
            except StopSearch:
                if not q.item:
                    status = Status.TIMEOUT
                    print("Queue was empty on timeout player: {} timeout: {}".format(player, time_limit)).replace("\n", " ")
                    break
            except Exception as err:
                status = Status.EXCEPTION
                print(ERR_INFO.format(err, initial_state, player, None, game, game_history))
                break

            action = q.item
            if action not in game.actions():
                status = Status.INVALID_MOVE
                print("Invalid move by player {} Tried: {} When options were: {}\nGame History: {}".format(
                    player, action, game.actions(), game_history))


        next_move = random.choice(game.actions())
        game = game.result(next_move)
        game_history.append(next_move)


    print("game over")
    print("game history", game_history)

    mm.player_id = 'mm'
    ab.player_id = 'ab'
    cust.player_id = 'cust'

    for player, bucket in zip(comparees, buckets):
        add_combined_stats(player, bucket)




#print(summarise_statistics(comparees))
#for player in comparees:
#    print(player.player_id, player.context)

for bucket in buckets:
    print(bucket)