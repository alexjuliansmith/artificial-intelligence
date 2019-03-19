import textwrap
from timeit import default_timer as timer

from isolation.isolation import Isolation
from isolation import fork_get_action, Empty, Status, ERR_INFO, StopSearch
from my_custom_player import *
from my_custom_player import IterativeDeepeningPlayer as ID
from sample_players import RandomPlayer

import queue
from copy import deepcopy

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
        self.context = deepcopy(player.context)  ## Freeze this at point of valid queue insertion




stats_to_combine = [METRIC_DEPTH,
                    METRIC_NODES_SEARCHED,
                    METRIC_TERMINAL_NODES_SEARCHED,
                    METRIC_BRANCHING_FACTOR]

def make_combined_statistics():
    return {
        key: defaultdict(lambda: (0,0) ) for key in stats_to_combine
    }

def add_combined_stats(player, combined_stats):
    for key in stats_to_combine:
        stat = player.context[key]
        for ply, value in stat.items():
            count, total = combined_stats[key][ply]
            combined_stats[key][ply] = (count + 1, total + value)


comparees = [ID_MinimaxPlayer, AlphaBetaPlayer, CustomPlayer]
buckets = [make_combined_statistics() for _ in range(len(comparees))]

num_matches = 3
time_limit = 5




for i in range(num_matches):
    mm = ID_MinimaxPlayer(0)
    ab = AlphaBetaPlayer(0)
    cust = CustomPlayer(0)
    players = [player(0) for player in comparees]

    initial_state = game = Isolation()
    game_history = []

    start = timer()
    while not game.terminal_test():
        for player in players:
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
            player.context = q.context  # Replace player context with the valid one

        next_move = random.choice(game.actions())
        game = game.result(next_move)
        game_history.append(next_move)

    duration = timer() - start
    num_moves = len(game_history)
    print("game over after %s moves and %.2f seconds (%d milliseconds per move)" % (num_moves, duration, duration / num_moves * 1000))
    #print("game history", game_history)


    for player, bucket in zip(players, buckets):
        add_combined_stats(player, bucket)




for id, type in enumerate(comparees):
    print(type)
    bucket = buckets[id]
    for stat, ply_values in bucket.items():
        #print(stat, ply_values)
        sum_total = sum(total for count, total in ply_values.values())
        sum_count = sum(count for count, total in ply_values.values())
        try:
            print("{}: Sum Total: {} Total Count: {} Average: {:.2f}".format(stat, sum_total, sum_count, sum_total / sum_count))
        except ZeroDivisionError:
            print("**{}: Sum Total: {} Total Count: {}  **".format(stat, sum_total, sum_count))
        print("ply\tcount\ttotal\t\tmean")
        for ply, value in ply_values.items():
            count, total = value
            print("{}\t{}\t\t{:<8}\t{:.2f}".format(ply, count, total, total / count))
        print("##############################")
    print("******************************")