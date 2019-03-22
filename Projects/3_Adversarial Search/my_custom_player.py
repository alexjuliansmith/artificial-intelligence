
import random
from collections import defaultdict
from timeit import default_timer as timer

from isolation import DebugState, Isolation
import isolation.isolation as isolation

from sample_players import DataPlayer, MinimaxPlayer


#######################################
# Instrumentation
##############################################################################
# This section defines metrics and decorators
# they will be used to instrument the search code to answer project questions
##############################################################################

# Global Constants that switch on metric gathering
INSTRUMENTATION_ON = True
SCORE_TIMING_ON = True  #TODO turn off

# Constants to provide consistent naming of common metrics
METRIC_BRANCHING_FACTOR = 'branching factor'
METRIC_DEPTH = 'depth completed'
METRIC_NODES_SEARCHED = "nodes searched"
METRIC_TERMINAL_NODES_SEARCHED = "terminal nodes searched"
METRIC_EVALUATION_NODES_SEARCHED = "evaluation nodes searched"
METRIC_SCORE_ELAPSED_TIME = "score fn elapsed time"


#  Decorators used to gather metrics for a) search nodes and b) score functions respectively
def instrument_node(search_node_method):
    def wrapper(self, state, depth, *args, **kwargs):
        self.context[METRIC_NODES_SEARCHED][state.ply_count] += 1
        if state.terminal_test():
            self.context[METRIC_TERMINAL_NODES_SEARCHED][state.ply_count] += 1
        elif depth <= 0:
            self.context[METRIC_EVALUATION_NODES_SEARCHED][state.ply_count] += 1

        return search_node_method(self, state, depth, *args, **kwargs)

    if INSTRUMENTATION_ON:
        return wrapper
    else:
        return search_node_method


def instrument_score(score_method):
    def wrapper(self, state, *args, **kwargs):
        start = timer()
        result = score_method(self, state, *args, **kwargs)
        self.context[METRIC_SCORE_ELAPSED_TIME][state.ply_count].append(timer() - start)
        return result

    if INSTRUMENTATION_ON and SCORE_TIMING_ON:
        return wrapper
    else:
        return score_method


######################################
# Bitboard functions
##############################################################################
# This section defines useful operations on bitboards
# they will be used by the custom Player and custom heuristics code
##############################################################################

bitboard = int  # type alias


def location_to_bitboard(location_index: int) -> bitboard:
    '''
    :param location_index: a board index
    :return:  bitboard with just the bit at that location set
    '''
    if location_index is None:
        return 0
    return 1 << location_index


def count_set_bits(board: bitboard) -> int:
    '''
    Kernighan’s  algorithm to count number of set bits in an integer.
    Can be used to find the number of flagged squares in a bitboard representation
    For instance, given the bitboard from the Isolation game state it will count the number of remaining empty squares
    :param board: an integer representing a bitboard
    :return: number of set bits in board
    '''
    bit_count = 0
    while board:
        board &= (board - 1)
        bit_count += 1
    return bit_count


#  Convert Action enum into a more useful format for the get_all_knight_moves function
KNIGHT_MOVE_BITSHIFTS = [int(a) for a in isolation.Action if a > 0]

def get_all_knight_moves(knights: bitboard, valid_squares: bitboard = None) -> bitboard:
    """
    Given
    knights: bitboard with locations of a set of knights
    valid_squares: optional bitboard identifying all squares that can be legally moved to
                    if provided then it is used to mask out invalid knights moves
    Return
    Bitboard with all squares that at least one knight can move to (doesn't include original knight positions)
    """
    moves = 0
    for kmbs in KNIGHT_MOVE_BITSHIFTS:
        moves |= (knights << kmbs)
        moves |= (knights >> kmbs)
    if valid_squares is not None:
        moves &= valid_squares
    return moves



######################################
# Custom Heuristics
######################################


def propagate_move_wavefronts(state: Isolation) -> (int, int, int, int):
    # Initialise bitboards
    active_wavefront = location_to_bitboard(state.locs[state.player()])
    inactive_wavefront = location_to_bitboard(state.locs[1 - state.player()])
    empty_squares = state.board
    active_controlled_squares = inactive_controlled_squares = 0
    # Initialise player wavefront counts
    active_wavefront_count = inactive_wavefront_count = 0

    # While at least one player can still make moves
    # For each player:
    # 1. Update the 'wavefront' bitboard by making all moves by all knights on the current wavefront
    # 2. Mask these potential moves against the empty (valid and still available) squares bitboard
    # 3. Remove the new wavefront squares from the empty squares bitboard
    # 4. Add the new wavefront squares to the cumulative player controlled squares bitboard
    # 5. If there are any valid moves in the new wavefront, increment the player's minimum number of moves
    while active_wavefront or inactive_wavefront:
        if active_wavefront:
            active_wavefront = get_all_knight_moves(active_wavefront)
            active_wavefront &= empty_squares
            empty_squares &= ~active_wavefront
            active_controlled_squares |= active_wavefront
            active_wavefront_count += (active_wavefront > 0)
        if inactive_wavefront:
            inactive_wavefront = get_all_knight_moves(inactive_wavefront)
            inactive_wavefront &= empty_squares
            empty_squares &= ~inactive_wavefront
            inactive_controlled_squares |= inactive_wavefront
            inactive_wavefront_count += (inactive_wavefront > 0)


    num_active_controlled_squares = count_set_bits(active_controlled_squares)
    num_inactive_controlled_squares = count_set_bits(inactive_controlled_squares)

    # Correctness Tests
    # assert not active_controlled_squares & inactive_controlled_squares
    # assert not (active_controlled_squares | inactive_controlled_squares) & empty_squares
    # assert num_active_controlled_squares + num_inactive_controlled_squares == count_set_bits(state.board) - count_set_bits(empty_squares)
    # assert active_wavefront_count <= num_active_controlled_squares
    # assert inactive_wavefront_count <= num_inactive_controlled_squares

    return active_wavefront_count, inactive_wavefront_count, \
           num_active_controlled_squares, num_inactive_controlled_squares

@instrument_score
def control_heuristic(player, state):
    """
    Heuristic estimation of the position value from player's perspective
    Returns the difference between:
      the number of squares the player can reach first (the squares the player 'controls')
      and the number of squares the player's opponent can reach first (the squares the opponent 'controls')
    """

    _, _, num_active_controlled_squares, num_inactive_controlled_squares = propagate_move_wavefronts(state)
    score = num_active_controlled_squares - num_inactive_controlled_squares

    if player.player_id == state.player():
        return score
    else:
        return -score

@instrument_score
def min_remaining_moves_heuristic(player, state):
    """
    Heuristic estimation of the position value from player's perspective
    'min remaining moves' is a lower bound (i.e. always less than or equal) on the actual number of moves
    a player can make even against opponent's best play.
    Returns the difference between:
      the player's min remaining moves and
      the opponent's min remaining moves
    """

    active_min_moves, inactive_min_moves, _, _ = propagate_move_wavefronts(state)
    score = active_min_moves - inactive_min_moves

    if player.player_id == state.player():
        return score
    else:
        return -score

@instrument_score
def combo_heuristic(player, state):
    """
    Heuristic estimation of the position value from player's perspective
    Returns
      the simple sum of the control and min remaining move heuristics
    """

    active_min_moves, inactive_min_moves, num_active_controlled_squares, num_inactive_controlled_squares = propagate_move_wavefronts(state)
    score = active_min_moves + num_active_controlled_squares - inactive_min_moves - num_inactive_controlled_squares

    if player.player_id == state.player():
        return score
    else:
        return -score



######################################
# Custom Players
######################################

WIN, LOSS = float("inf"), float("-inf")


class IterativeDeepeningPlayer(DataPlayer):

    SEARCH_DEPTH_LIMIT = None  # Fixed depth to limit iterative deepening, can be overridden in subclass
    score = instrument_score(MinimaxPlayer.score)  # Default heuristic, can be overridden in subclass

    def __init__(self, player_id):
        super().__init__(player_id)
        if INSTRUMENTATION_ON:
            ## initialise  metrics
            self.context = {}
            self.context[METRIC_BRANCHING_FACTOR] = {}
            self.context[METRIC_DEPTH] = defaultdict(int)
            self.context[METRIC_NODES_SEARCHED] = defaultdict(int)
            self.context[METRIC_TERMINAL_NODES_SEARCHED] = defaultdict(int)
            self.context[METRIC_EVALUATION_NODES_SEARCHED] = defaultdict(int)
            self.context[METRIC_SCORE_ELAPSED_TIME] = defaultdict(list)


    def get_action(self, state):

        try:
            # Seed the queue, so we always have a move after timeout
            self.queue.put(random.choice(state.actions()))
        except IndexError:
            # Active Player has no legal moves, just return (leaving the queue empty)
            return

        # If this is not player's first move, progressively improve the seed move using an iterative deepening search
        if state.ply_count >= 2:
            if INSTRUMENTATION_ON:
                self.context[METRIC_BRANCHING_FACTOR][state.ply_count] = len(state.actions())

            # Continue iterative deepening until we run out of time, free aquares or reach fixed search depth limit
            free_squares = count_set_bits(state.board)
            max_search_depth = min(self.SEARCH_DEPTH_LIMIT, free_squares) if self.SEARCH_DEPTH_LIMIT else free_squares

            for depth in range(1, max_search_depth + 1):
                best_score, best_move = self.search(state, depth)

                if INSTRUMENTATION_ON:
                    self.context[METRIC_DEPTH][state.ply_count] = depth

                self.queue.put(best_move)
                if best_score in (WIN, LOSS):
                    break  # Forced result, no need to use up the rest of the search time

    def search(self, state, depth: int):
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

    @instrument_node
    def min_value(self, state, depth, alpha, beta):

        moves = state.actions()
        if not moves:
            return WIN, None  # No available moves, opponent has lost
        if get_all_knight_moves(location_to_bitboard(state.locs[self.player_id]), state.board) == 0:
            return LOSS, moves[0]  # Active player has no moves left, any opponent move wins
        if depth <= 0:
            return self.score(state), None  # Leaf search node, evaluate position instead of moving

        # Find best move for opponent
        best_score, best_move = WIN, moves[0]
        for move in moves:
            score, _ = self.max_value(state.result(move), depth - 1, alpha, beta)
            if score < best_score:
                if score <= alpha:
                    return score, move  # Active player has an equal or better move choice, stop searching this line
                best_score, best_move = score, move
                beta = min(beta, score)

        return best_score, best_move


    @instrument_node
    def max_value(self, state, depth, alpha, beta):

        moves = state.actions()
        if not moves:
            return LOSS, None  # No available moves, active player has lost
        if get_all_knight_moves(location_to_bitboard(state.locs[1 - self.player_id]), state.board) == 0:
            return WIN, moves[0]  # Opponent has no moves left, any active player move wins
        if depth <= 0:
            return self.score(state), None  # Leaf search node, evaluate position instead of moving

        # Find best move for active player
        best_score, best_move = LOSS, moves[0]
        for move in moves:
            score, _ = self.min_value(state.result(move), depth-1, alpha, beta)
            if score > best_score:
                if score >= beta:
                    return score, move  # Opponent has an equal or better move choice, stop searching this line
                best_score, best_move = score, move
                alpha = max(alpha, score)

        return best_score, best_move

class ID_MinimaxPlayer(IterativeDeepeningPlayer):

    def search(self, state, depth):
        move_scores = [(self.min_value(state.result(action), depth - 1), action) for action in state.actions()]
        return max(move_scores)

    @instrument_node
    def min_value(self, state, depth):
        if state.terminal_test(): return state.utility(self.player_id)
        if depth <= 0: return self.score(state)
        value = float("inf")
        for action in state.actions():
            value = min(value, self.max_value(state.result(action), depth - 1))
        return value

    @instrument_node
    def max_value(self, state, depth):
        if state.terminal_test(): return state.utility(self.player_id)
        if depth <= 0: return self.score(state)
        value = float("-inf")
        for action in state.actions():
            value = max(value, self.min_value(state.result(action), depth - 1))
        return value

class VerifyEquivalencePlayer(IterativeDeepeningPlayer):

    def __init__(self, player_id):
        super().__init__(player_id)
        self.alphabetaPlayer = AlphaBetaPlayer(player_id)
        self.minimaxPlayer = ID_MinimaxPlayer(player_id)

    def search(self, state, depth):
        ab_score, ab_move = self.alphabetaPlayer.search(state, depth)
        mm_score, mm_move = self.minimaxPlayer.search(state, depth)

        if ab_score != mm_score:
            print("AB Score {} Move {}\nMM Score {} Move {}".format(ab_score, ab_move, mm_score, mm_move))
            debug = DebugState.from_state(state)
            print("Active Player: ", debug.player_symbols[self.player_id])
            print("Ply: ", state.ply_count)
            print("Search Depth: ", depth)
            print(debug)

        return ab_score, ab_move or mm_move


######################################
# Putting it all together
######################################

'''
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
        import random
        self.queue.put(random.choice(state.actions()))
'''

#IterativeDeepeningPlayer.SEARCH_DEPTH_LIMIT = 1  Use this to compare players with a fixed-depth search limit

class CustomPlayer(AlphaBetaPlayer):
    #pass
    #score = min_remaining_moves_heuristic
    #score = control_heuristic
    score = combo_heuristic




