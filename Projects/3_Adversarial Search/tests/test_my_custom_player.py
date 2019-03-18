
import unittest

from collections import deque
from random import choice
from textwrap import dedent

from isolation import Isolation, Agent, fork_get_action, play
from sample_players import RandomPlayer
from my_custom_player import CustomPlayer, IterativeDeepeningPlayer as ID, ID_MinimaxPlayer, AlphaBetaPlayer


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


class BaseCustomPlayerTest(unittest.TestCase):
    def setUp(self):
        self.time_limit = 150
        self.move_0_state = Isolation()
        self.move_1_state = self.move_0_state.result(choice(self.move_0_state.actions()))
        self.move_2_state = self.move_1_state.result(choice(self.move_1_state.actions()))
        terminal_state = self.move_2_state
        while not terminal_state.terminal_test():
            terminal_state = terminal_state.result(choice(terminal_state.actions()))
        self.terminal_state = terminal_state


class CustomPlayerGetActionTest(BaseCustomPlayerTest):
    def _test_state(self, state):
        agent = CustomPlayer(state.ply_count % 2)
        action = fork_get_action(state, agent, self.time_limit)
        self.assertTrue(action in state.actions(), dedent("""\
            Your agent did not call self.queue.put() with a valid action \
            within {} milliseconds from state {}
        """).format(self.time_limit, state))
        #print(agent.context)
        summary = summarise_statistics([agent])
        for id, metrics in summary.items():
            print (id)
            for item in metrics.items():
                print(item)

    def test_get_action_player1(self):
        """ get_action() calls self.queue.put() before timeout on an empty board """
        self._test_state(self.move_0_state)

    def test_get_action_player2(self):
        """ get_action() calls self.queue.put() before timeout as player 2 """
        self._test_state(self.move_1_state)

    def test_get_action_midgame(self):
        """ get_action() calls self.queue.put() before timeout in a game in progress """
        self._test_state(self.move_2_state)

    def test_get_action_terminal(self):
        """ get_action() calls self.queue.put() before timeout when the game is over """
        self._test_state(self.terminal_state)


class CustomPlayerPlayTest(BaseCustomPlayerTest):

    def test_custom_player_vs_mini(self):
        """ CustomPlayer successfully completes a game against standard minimax """
        agents = (Agent(CustomPlayer, "Player 1"),
                  Agent(ID_MinimaxPlayer, "Player 2"))
        initial_state = Isolation()
        winner, game_history, _, players = play((agents, initial_state, self.time_limit, 0))

        state = initial_state
        moves = deque(game_history)
        while moves: state = state.result(moves.popleft())

        self.assertTrue(state.terminal_test(), "Your agent did not play until a terminal state.")

        print("winner: ", winner)
        summary = summarise_statistics(players)
        for id, metrics in summary.items():
            print (id)
            for item in metrics.items():
                print(item)


    def test_custom_player_vs_ab(self):
        """ CustomPlayer successfully completes a game against standard alphabeta """
        agents = (Agent(CustomPlayer, "Player 1"),
                  Agent(AlphaBetaPlayer, "Player 2"))
        initial_state = Isolation()
        winner, game_history, _, players = play((agents, initial_state, self.time_limit, 0))

        state = initial_state
        moves = deque(game_history)
        while moves: state = state.result(moves.popleft())

        self.assertTrue(state.terminal_test(), "Your agent did not play until a terminal state.")

        print("winner: ", winner)
        summary = summarise_statistics(players)
        for id, metrics in summary.items():
            print (id)
            for item in metrics.items():
                print(item)



    def test_custom_player(self):
        """ CustomPlayer successfully completes a game against itself """
        agents = (Agent(CustomPlayer, "Player 1"),
                  Agent(CustomPlayer, "Player 2"))
        initial_state = Isolation()
        winner, game_history, _, players = play((agents, initial_state, self.time_limit, 0))
        
        state = initial_state
        moves = deque(game_history)
        while moves: state = state.result(moves.popleft())

        self.assertTrue(state.terminal_test(), "Your agent did not play until a terminal state.")


        summary = summarise_statistics(players)
        print("winner: ", winner)
        for id, metrics in summary.items():
            print (id)
            for item in metrics.items():
                print(item)



