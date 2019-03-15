
import random

#from isolation import *
import isolation.isolation as isolation

from sample_players import DataPlayer, MinimaxPlayer



WIN, LOSS = float("inf"), float("-inf")

MOVE_BIT_SHIFTS = [int(a) for a in isolation._ACTIONSET if a > 0]
BOARD_MASK = isolation._BLANK_BOARD

######################################
# Bitboard functions
#####################################

def count_bits(integer):
    '''
    Kernagham algorithm to count number of set bits in an integer
    Can be used to find the number of flagged squares in a bitboard representation
    For instance, in the bitboard representation of the game state it will count the number of remaining free squares
    :param integer:
    :return: number of set bits in integer
    '''
    bit_count = 0
    while integer:
        integer &= (integer - 1)
        bit_count += 1
    return bit_count

def get_knight_moves(knights, valid_squares):
    """
    Given
    knights: bitboard with locations of a set of knights
    valid_squares: bitboard identifying all squares that can be legally moved to
    Return
    Bitboard with all valid squares that any knight can move to (doesn't include original knight positions)
    """
    moves = 0
    for mbs in MOVE_BIT_SHIFTS:
        moves |= (knights << mbs)
        moves |= (knights >> mbs)
    moves &= valid_squares
    return moves



######################################
# Bitboard functions
#####################################

######################################
# Custom Players
#####################################

class IterativeDeepeningPlayer(DataPlayer):

    score = MinimaxPlayer.score  # Default heuristic, can be overridden in subclass

    def get_action(self, state):

        try:
            # Seed the queue, so we always have a move after timeout
            self.queue.put(random.choice(state.actions()))
        except IndexError:
            # Active Player has no legal moves, just return leaving the queue empty
            return

        # If this is not player's first move, progressively improve the seed move using an iterative deepening search
        if state.ply_count >= 2:
            # Continue iterative deepening until we run out of free aquares (or time)
            free_squares = count_bits(state.board)
            for depth in range(free_squares):
                best_score, best_move = self.search(state, depth + 1)
                self.queue.put(best_move)
                if best_score in (WIN, LOSS):
                    break  # Forced result, no need to use up the rest of the search time

    def search(self, state, depth):
        '''
        Abstract method to be implemented in subclasses
        :param state: Game State
        :param depth: Requested search move depth
        :return: Pair (best_score, best_move)
        representing the best action found and its (heuristic or game theoretic) score
        (If subclasses only want to return an action, they can return None for best_score)
        '''
        raise NotImplementedError

class AlphaBetaPlayer(IterativeDeepeningPlayer):

    def search(self, state, depth):
        return self.max_value(state, depth, LOSS, WIN)

    def min_value(self, state, depth, alpha, beta):

        moves = state.actions()
        if not moves:
            return WIN, None  # No available moves, opponent has lost
        if not state._has_liberties(self.player_id):
            return LOSS, moves[0]  # Active player has no moves left, any opponent move wins
        if depth <= 0:
            return self.score(state), None  # Leaf search node, evaluate position instead of moving

        # Find best move for opponent
        best_score, best_move = WIN, moves[0]
        for move in moves:
            score, _ = self.max_value(state.result(move), depth - 1, alpha, beta)
            if score < best_score:
                if score <= alpha:
                    return score, move  # Maximising player has an equal or better move choice, stop searching this line
                best_score, best_move = score, move
                beta = min(beta, score)

        return best_score, best_move


    def max_value(self, state, depth, alpha, beta):

        moves = state.actions()
        if not moves:
            return LOSS, None  # No available moves, active player has lost
        if not state._has_liberties(1 - self.player_id):
            return WIN, moves[0]  # Opponent has no moves left, any active player move wins
        if depth <= 0:
            return self.score(state), None  # Leaf search node, evaluate position instead of moving

        # Find best move for active player
        best_score, best_move = LOSS, moves[0]
        for move in moves:
            score, _ = self.min_value(state.result(move), depth-1, alpha, beta)
            if score > best_score:
                if score >= beta:
                    return score, move  # Minimising player has an equal or better move choice, stop searching this line
                best_score, best_move = score, move
                alpha = max(alpha, score)

        return best_score, best_move

class ID_MinimaxPlayer(IterativeDeepeningPlayer):

    def search(self, state, depth):
        def min_value(state, depth):
            if state.terminal_test(): return state.utility(self.player_id)
            if depth <= 0: return self.score(state)
            value = float("inf")
            for action in state.actions():
                value = min(value, max_value(state.result(action), depth - 1))
            return value

        def max_value(state, depth):
            if state.terminal_test(): return state.utility(self.player_id)
            if depth <= 0: return self.score(state)
            value = float("-inf")
            for action in state.actions():
                value = max(value, min_value(state.result(action), depth - 1))
            return value

        results = [(min_value(state.result(action), depth - 1), action) for action in state.actions()]
        return max(results)

class VerifyEquivalencePlayer(AlphaBetaPlayer, ID_MinimaxPlayer):

    def search(self, state, depth):
        ab_score, ab_move = AlphaBetaPlayer.search(self, state, depth)
        mm_score, mm_move = ID_MinimaxPlayer.search(self, state, depth)

        if ab_score != mm_score:
            print("AB Score {} Move {}\nMM Score {} Move {}".format(ab_score, ab_move, mm_score, mm_move))
            debug = DebugState.from_state(state)
            print("Active Player: ", debug.player_symbols[self.player_id])
            print("Ply: ", state.ply_count)
            print("Search Depth: ", depth)
            print(debug)

        return ab_score, ab_move or mm_move

######################################
# Custom Players
#####################################

class CustomPlayer(DataPlayer):

    """ Implement your own agent to play knight's Isolation

    The get_action() method is the only required method for this project.
    You can modify the interface for get_action by adding named parameters
    with default values, but the function MUST remain compatible with the
    default interface.

    **********************************************************************
    NOTES:
    - The test cases will NOT be run on a machine with GPU access, nor be
      suitable for using any other machine learning techniques.

    - You can pass state forward to your agent on the next turn by assigning
      any pickleable object to the self.context attribute.
    **********************************************************************
    """
    def get_action(self, state):
        """ Employ an adversarial search technique to choose an action
        available in the current state calls self.queue.put(ACTION) at least

        This method must call self.queue.put(ACTION) at least once, and may
        call it as many times as you want; the caller will be responsible
        for cutting off the function after the search time limit has expired.

        See RandomPlayer and GreedyPlayer in sample_players for more examples.

        **********************************************************************
        NOTE: 
        - The caller is responsible for cutting off search, so calling
          get_action() from your own code will create an infinite loop!
          Refer to (and use!) the Isolation.play() function to run games.
        **********************************************************************
        """
        # TODO: Replace the example implementation below with your own search
        #       method by combining techniques from lecture
        #
        # EXAMPLE: choose a random move without any search--this function MUST
        #          call self.queue.put(ACTION) at least once before time expires
        #          (the timer is automatically managed for you)
        ##import random
        ##self.queue.put(random.choice(state.actions()))


CustomPlayer = AlphaBetaPlayer
CustomPlayer = ID_MinimaxPlayer
CustomPlayer = VerifyEquivalencePlayer