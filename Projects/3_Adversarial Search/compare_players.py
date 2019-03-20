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
        #self.context = deepcopy(player.context)  ## Freeze this at point of valid queue insertion




stats_to_combine = [METRIC_DEPTH,
                    METRIC_NODES_SEARCHED,
                    METRIC_TERMINAL_NODES_SEARCHED,
                    METRIC_EVALUATION_NODES_SEARCHED,
                    METRIC_BRANCHING_FACTOR]

list_stats = [METRIC_SCORE_ELAPSED_TIME]

ALL_NODES = "ALL nodes searched"
ALL_TERMINAL = "ALL terminal nodes searched"
ALL_EVALUATION = "ALL evaluation nodes searched"

extras = [ALL_NODES, ALL_TERMINAL, ALL_EVALUATION]
extras = []
stats_to_combine += extras

if SCORE_TIMING_ON:
    stats_to_combine += list_stats

def make_combined_statistics():
    return {
        key: defaultdict(lambda: (0,0) ) for key in stats_to_combine
    }

def add_combined_stats(player, combined_stats):
    for stat_name in stats_to_combine:
        stat = player.context[stat_name]
        for ply, value in stat.items():
            count, total = combined_stats[stat_name][ply]
            if (stat_name in list_stats):
                combined_stats[stat_name][ply] = (count + len(value), total + (sum(value) * 1000000))  #convert to microseconds
            else:
                combined_stats[stat_name][ply] = (count + 1, total + value)


comparees = [ID_MinimaxPlayer, AlphaBetaPlayer, CustomPlayer]
buckets = [make_combined_statistics() for _ in range(len(comparees))]
total_moves = num_games = 0

num_matches = 100
time_limit = 150




for i in range(num_matches):

    players = [player(0) for player in comparees]

    for player in players:
        for metric in extras:
            player.context[metric] = defaultdict(int)



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
            '''if game.ply_count > 1:
                q.context[ALL_NODES][game.ply_count] = player.context[METRIC_NODES_SEARCHED][game.ply_count]
                q.context[ALL_TERMINAL][game.ply_count] = player.context[METRIC_TERMINAL_NODES_SEARCHED][game.ply_count]
                q.context[ALL_EVALUATION][game.ply_count] = player.context[METRIC_EVALUATION_NODES_SEARCHED][game.ply_count]
            player.context = q.context  # Replace player context with the valid one
            '''

        next_move = random.choice(game.actions())
        game = game.result(next_move)
        game_history.append(next_move)

    duration = timer() - start
    num_moves = len(game_history)
    total_moves += num_moves
    num_games += 1
    print("game over after %s moves and %.2f seconds (%d milliseconds per move)" % (num_moves, duration, duration / num_moves * 1000))
    #print("game history", game_history)


    for player, bucket in zip(players, buckets):
        add_combined_stats(player, bucket)


if SCORE_TIMING_ON:
    for player in players:
        print(player, player.context[METRIC_SCORE_ELAPSED_TIME])

print("AVERAGE MOVES PER GAME:", total_moves / num_games)

##############  Summary Table
print("******************* SUMMARY TABLE***************\n")
print(",,Total,Count,Mean")
for id, type in enumerate(comparees):
    print(type)
    bucket = buckets[id]
    for stat in stats_to_combine:
        ply_values = bucket[stat]
        sum_total = sum(total for _, total in ply_values.values())
        sum_count = sum(count for count, _ in ply_values.values())
        try:
            print(",{},{},{},{:.2f}".format(stat, sum_total, sum_count, sum_total / sum_count))
        except ZeroDivisionError:
            print("**{}: Sum Total: {} Total Count: {}  **".format(stat, sum_total, sum_count))
        plies, counts, totals, means = [], [], [], []

print("\n\n******************* CHART COMPARISON ***************\n")

max_ply = max(ply for ply in buckets[0][METRIC_BRANCHING_FACTOR])


for stat in stats_to_combine:
    print(stat)
    for id, type in enumerate(comparees):
        plies, counts, totals, means = [], [], [], []
        print(type)
        for ply in range(2, max_ply + 1):
                count, total = buckets[id][stat][ply]
                plies.append(str(ply))
                counts.append(str(count))
                totals.append(str(total))
                means.append("{:.2f}".format(total/count if count else 0))
        print(",PLY,", ",".join(plies))
        print(",COUNT,", ",".join(counts))
        print(",TOTAL,", ",".join(totals))
        print(",MEAN,", ",".join(means))

