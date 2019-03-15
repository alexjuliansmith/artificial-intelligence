
from sample_players import DataPlayer, MinimaxPlayer


WIN, LOSS = float("inf"), float("-inf")


class AlphaBetaPlayerBASIC(DataPlayer):

    score = MinimaxPlayer.score


    def get_action(self, state):


        if state.ply_count < 2:
            self.queue.put(random.choice(state.actions())) ## Seed the queue, so we always have a move

        else:
        # If this is not player's first move,  search using alphabeta with iterative deepening
            depth = 0
            while True:
                depth += 1
                best_move, best_score = self.alphabeta(state, depth)
                self.queue.put(best_move)
                if best_score in (WIN, LOSS):
                    break  # Forced result, no need to use up the rest of the search time

    def alphabeta(self, state, depth, alpha=LOSS, beta=WIN):
        move_scores = []
        for move in state.actions():
            score = self.min_value(state.result(move), depth, LOSS, WIN)
            if score == WIN:
                return move, score # Move is guaranteed win, no need to search further
            move_scores.append((move, score))

        return max(move_scores, key=lambda x: x[1])

    #return max(state.actions(), key=lambda x: min_value(state.result(x), depth - 1))

    def min_value(self, state, depth, alpha, beta):

        if state.terminal_test():
            return state.utility(self.player_id)
        if depth <= 0:
            return self.score(state)

        moves = state.actions()
        best_score = WIN
        for move in moves:
            score = self.max_value(state.result(move), depth - 1, alpha, beta)
            if score < best_score:
                if score <= alpha:
                    return score
                best_score = score
                beta = min(beta, score)

        return best_score


    def max_value(self, state, depth, alpha, beta):
        if state.terminal_test():
            return state.utility(self.player_id)
        if depth <= 0:
            return self.score(state)

        moves = state.actions()
        best_score = LOSS
        for move in moves:
            score = self.min_value(state.result(move), depth-1, alpha, beta)
            if score > best_score:
                if score >= beta:
                    return score
                best_score = score
                alpha = max(alpha, score)

        return score




