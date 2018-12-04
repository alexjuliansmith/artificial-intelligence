
from itertools import chain, combinations
from functools import lru_cache, reduce
from aimacode.planning import Action
from aimacode.utils import Expr
from collections import defaultdict
from layers import BaseLayer, BaseLiteralLayer, makeNoOp, make_node, ActionNode
from operator import or_
#################################

literal_indexes, action_indexes = [], []

def literal_index(literal, _indexes = {}):
    try:
        return _indexes[literal]
    except KeyError:
        _indexes[literal] = 1 << len(_indexes)
        literal_indexes.append(literal)
        return _indexes[literal]

def action_index(action, _indexes = {}):
    try:
        return _indexes[action]
    except KeyError:
        _indexes[action] = 1 << len(_indexes)
        action_indexes.append(action)
        return _indexes[action]

def list_items(items, item_list):
    index = 0
    result = set()
    while items:
        if items & 1:
            result.add(item_list[index])
        items >>= 1
        index += 1
    return result


class FastLiteralNode(Expr):
    __slots__ = ['__negation']
    def __init__(self, op, *args):
        super().__init__(op, *args)
        self.__negation = args[0] if '~' == op else FastLiteralNode('~', self)

    def __invert__(self):
        return self.__negation

@lru_cache(None)
def make_FastLiteralNode(literal: Expr):
    return FastLiteralNode(literal.op, *literal.args)

class FastActionNode(ActionNode):
    __slots__ = ['index', 'preconditions_vector', 'effects_vector', 'negated_effects_vector']
    def __init__(self, symbol, preconditions, effects, no_op):
        super().__init__(symbol, preconditions, effects, no_op)
        self.index = action_index(self)
        self.preconditions_vector = self.effects_vector = self.negated_effects_vector = 0
        for p in self.preconditions:
            self.preconditions_vector |= literal_index(p)
        for e in self.effects:
            self.effects_vector |= literal_index(e)
            self.negated_effects_vector |= literal_index(~e)

    def __lt__(self, other):
        self.index < other.index

@lru_cache(None)
def make_FastActionNode(action, no_op=False):
    preconditions =  {make_FastLiteralNode(p) for p in action.precond_pos} | \
                    {~make_FastLiteralNode(p) for p in action.precond_neg}

    effects = {make_FastLiteralNode(e) for e in action.effect_add} | \
             {~make_FastLiteralNode(e) for e in action.effect_rem}

    return FastActionNode(str(action), frozenset(preconditions), frozenset(effects), no_op)

##################################

make_node = make_FastActionNode

##################################
@lru_cache(None)
def _inconsistent_effects(actionA, actionB):
    """ Return True if an effect of one action negates an effect of the other
    Factored outside class to enable caching across ActionLayer instances
    """
    try:
        return actionA.effects_vector & actionB.negated_effects_vector
    except AttributeError:
        # raise AttributeError("Should only occur on Test 1")
        # This branch necessary to pass some Test_1_InconsistentEffectsMutex unittests which build their own ActionNode
        return any(~effectB in actionA.effects for effectB in actionB.effects)

@lru_cache(None)
def _interference(actionA: ActionNode, actionB: ActionNode):
    """ Return True if the effects of either action negate the preconditions of the other
    Factored outside class to enable caching across ActionLayer instances
    """
    try:
        return actionA.preconditions_vector & actionB.negated_effects_vector \
            or actionB.preconditions_vector & actionA.negated_effects_vector
    except AttributeError:
        # raise AttributeError("Should only occur on Test 2")
        # This branch necessary to pass some Test_2_InterferenceMutex unittests which build their own ActionNode
        return any(~precondA in actionB.effects for precondA in actionA.preconditions) \
            or any(~precondB in actionA.effects for precondB in actionB.preconditions)


class ActionLayer(BaseLayer):

    def __init__(self, actions=[], parent_layer=None, serialize=True, ignore_mutexes=False):
        super().__init__(actions, parent_layer, ignore_mutexes)
        self._serialize=serialize
        self._new_actions = set()
        self._mutex_vector = defaultdict(int)
        self._preconditions_mutex_vector = {}  # The literals that are mutex with any of an action's preconditions
        try:
            self._static_mutex_vector = actions._static_mutex_vector
            self._mutexes = actions._mutexes
        except:
            self._static_mutex_vector = defaultdict(int)

    def add(self, action: ActionNode):
        assert action not in self, "Error: Action can only be added once"
        self._new_actions.add(action)
        super().add(action)

    def is_mutex(self, itemA, itemB):
        return itemA.index & (self._mutex_vector[itemB] | self._static_mutex_vector[itemB])

    def set_static_mutex(self, itemA, itemB):
        self._static_mutex_vector[itemA] |= itemB.index
        self._static_mutex_vector[itemB] |= itemA.index

    def set_mutex_vector(self, itemA, itemB):
        self._mutex_vector[itemA] |= itemB.index
        self._mutex_vector[itemB] |= itemA.index

    def set_mutex(self, itemA, itemB):
        super().set_mutex(itemA, itemB)
        self.set_mutex_vector(itemA, itemB)

    def relax_mutex(self, itemA, itemB):
        self._mutexes[itemA].discard(itemB)
        self._mutexes[itemB].discard(itemA)
        self._mutex_vector[itemA] ^= itemB.index
        self._mutex_vector[itemB] ^= itemA.index

    def update_mutexes(self):
        # Recheck all temporary mutexes from previous action layer, add to this layer if still mutex
        if not self._ignore_mutexes:
            for actionA in self._mutexes:
                for actionB in self._mutexes[actionA]:
                    relaxations = []
                    if self._competing_needs(actionA, actionB):
                        self.set_mutex_vector(actionA, actionB)
                    else:
                        relaxations.append(actionB)
                for actionB in relaxations:
                    self.relax_mutex(actionA, actionB)
        # Test actions newly added in this layer against all actions in layer to find any new mutexes
        for actionA in self._new_actions:
            for actionB in self:
                if actionA != actionB and not self.is_mutex(actionA, actionB):
                    if self._serialize and actionA.no_op == actionB.no_op == False:
                        self.set_static_mutex(actionA, actionB)
                    elif (self._inconsistent_effects(actionA, actionB)
                          or self._interference(actionA, actionB)):
                        self.set_static_mutex(actionA, actionB)
                    elif self._ignore_mutexes:
                        continue
                    elif self._competing_needs(actionA, actionB):
                        self.set_mutex(actionA, actionB)

    def add_inbound_edges(self, action, literals):
        pass

    def add_outbound_edges(self, action, literals):
        pass

    def _inconsistent_effects(self, actionA, actionB):
        """ Return True if an effect of one action negates an effect of the other

        Hints:
            (1) `~Literal` can be used to logically negate a literal
            (2) `self.children` contains a map from actions to effects

        See Also
        --------
        layers.ActionNode
        """
        # DONE: implement this function
        return _inconsistent_effects(actionA, actionB)

    def _interference(self, actionA, actionB):
        """ Return True if the effects of either action negate the preconditions of the other 

        Hints:
            (1) `~Literal` can be used to logically negate a literal
            (2) `self.parents` contains a map from actions to preconditions
        
        See Also
        --------
        layers.ActionNode
        """
        # DONE: implement this function
        return _interference(actionA, actionB)

    def _competing_needs(self, actionA, actionB):
        """ Return True if any preconditions of the two actions are pairwise mutex in the parent layer

        Hints:
            (1) `self.parent_layer` contains a reference to the previous literal layer
            (2) `self.parents` contains a map from actions to preconditions
        
        See Also
        --------
        layers.ActionNode
        layers.BaseLayer.parent_layer
        """
        # DONE: implement this function

        if isinstance(actionA, FastActionNode):
            try:
                actionB_preconditions_mutex_vector =  self._preconditions_mutex_vector[actionB]
            except KeyError:
                actionB_preconditions_mutex_vector =  self._preconditions_mutex_vector[actionB] = \
                    reduce(or_, (self.parent_layer._mutex_vector[p] for p in actionB.preconditions))
            return actionA.preconditions_vector & actionB_preconditions_mutex_vector

        # raise AttributeError("Should only occur on test 4")
        # This branch necessary to pass some Test_4_CompetingNeedsMutex unittests which build their own ActionNode
        return any(self.parent_layer.is_mutex(precondA, precondB)
                   for precondA in actionA.preconditions for precondB in actionB.preconditions)



class LiteralLayer(BaseLiteralLayer):

    def __init__(self, literals=[], parent_layer=None, ignore_mutexes=False):
        super().__init__(literals, parent_layer, ignore_mutexes)
        self._new_literals = set()
        self._mutex_vector = defaultdict(int)
        self._achievers_vector = {} # The actions which can achieve this fact
        self._achievers_mutex_vector = {} # The actions which are mutex with all the achievers of this fact
        #TODO quick hack to get static mutexes in literal layer
        for literal in iter(self):
            self._mutex_vector[literal] = literal_index(~literal)

    def _inconsistent_support(self, literalA, literalB):
        """ Return True if all ways to achieve both literals are pairwise mutex in the parent layer

        Hints:
            (1) `self.parent_layer` contains a reference to the previous action layer
            (2) `self.parents` contains a map from literals to actions in the parent layer

        See Also
        --------
        layers.BaseLayer.parent_layer
        """
        from operator import and_
        # DONE: implement this function
        causes_A, causes_B = self.parents[literalA], self.parents[literalB]
        # Implementation is equivalent to:
        # return all(self.parent_layer.is_mutex(causeA, causeB) for causeA in causes_A for causeB in causes_B)
        try:
            literalA_achievers_vector = self._achievers_vector[literalA]
        except KeyError:
            literalA_achievers_vector = self._achievers_vector[literalA] = \
                reduce(or_, (action.index for action in causes_A))

        try:
            literalB_achievers_mutex_vector = self._achievers_mutex_vector[literalB]
        except KeyError:
            literalB_achievers_mutex_vector = self._achievers_mutex_vector[literalB] = \
                reduce(and_, (self.parent_layer._mutex_vector[action]| self.parent_layer._static_mutex_vector[action]
                              for action in causes_B))
        return (literalA_achievers_vector & literalB_achievers_mutex_vector) == literalA_achievers_vector


    def _negation(self, literalA, literalB):
        """ Return True if two literals are negations of each other """
        # DONE: implement this function
        return literalA == ~literalB

################  Add Faster implementation

    def add(self, literal):
       if literal not in self:
            self._new_literals.add(literal)
            super().add(literal)

    def add_outbound_edges(self, action, literals):
        pass

    def is_mutex(self, itemA, itemB):
        return itemA == ~itemB or itemA in self._mutexes[itemB]

    def set_mutex(self, itemA, itemB):
        super().set_mutex(itemA, itemB)
        self._mutex_vector[itemA] |= literal_index(itemB)
        self._mutex_vector[itemB] |= literal_index(itemA)

    def update_mutexes(self):
        if not self._ignore_mutexes:
            # Recheck all dynamic mutexes from previous literal layer (if there is one), add to this layer if still mutex
            if self.parent_layer:
                for literalA in self.parent_layer.parent_layer._mutexes:
                    for literalB in self.parent_layer.parent_layer._mutexes[literalA]:
                        if self._inconsistent_support(literalA, literalB):
                            self.set_mutex(literalA, literalB)
            # Test literals newly added in this layer against all literals in layer to find any new mutexes
            for literalA in self._new_literals:
                for literalB in self:
                    if literalA != literalB != ~literalB:
                        if self._inconsistent_support(literalA, literalB):
                            self.set_mutex(literalA, literalB)

class PlanningGraph:
    def __init__(self, problem, state, serialize=True, ignore_mutexes=False):
        """
        Parameters
        ----------


        problem : PlanningProblem
            An instance of the PlanningProblem class

        state : tuple(bool)
            An ordered sequence of True/False values indicating the literal value
            of the corresponding fluent in problem.state_map

        serialize : bool
            Flag indicating whether to serialize non-persistence actions. Actions
            should NOT be serialized for regression search (e.g., GraphPlan), and
            _should_ be serialized if the planning graph is being used to estimate
            a heuristic
        """
        self._serialize = serialize
        self._is_leveled = False
        self._ignore_mutexes = ignore_mutexes
        self.goal = set(problem.goal)
        # Seed problem state map with FastLiterals to avoid constant creation of new negative literal instances
        problem.state_map = [make_FastLiteralNode(literal) for literal in problem.state_map]

        # make no-op actions that persist every literal to the next layer
        no_ops = [make_node(n, no_op=True) for n in chain(*(makeNoOp(s) for s in problem.state_map))]
        self._actionNodes = no_ops + [make_node(a) for a in problem.actions_list]
        
        # initialize the planning graph by finding the literals that are in the
        # first layer and finding the actions they they should be connected to
        literals = [s if f else ~s for f, s in zip(state, problem.state_map)]
        layer = LiteralLayer(literals, ActionLayer(), self._ignore_mutexes)
        layer.update_mutexes()
        self.literal_layers = [layer]
        self.action_layers = []


    @lru_cache(None)
    def _level_costs(self):
        '''
        :return: List of the level cost of each goal (the first level at which each goal appears in the PG)
        in level order
        Used by h_levelsum and h_maxlevel
        Note: method assumes PG has not yet been extended.
        '''
        goals_remaining = set(self.goal)
        level_costs = []
        level = 0
        while not self._is_leveled:
            new_goals_met = goals_remaining & self.literal_layers[level]
            level_costs += [level] * len(new_goals_met)
            goals_remaining -= new_goals_met
            if not goals_remaining:
                return level_costs
            self._extend()
            level += 1

        raise Exception("Planning graph doesn't contain a possible solution for any of the individual goals: %s" % goals_remaining)

    def h_levelsum(self):
        """ Calculate the level sum heuristic for the planning graph

        The level sum is the sum of the level costs of all the goal literals
        combined. The "level cost" to achieve any single goal literal is the
        level at which the literal first appears in the planning graph. Note
        that the level cost is **NOT** the minimum number of actions to
        achieve a single goal literal.
        
        For example, if Goal_1 first appears in level 0 of the graph (i.e.,
        it is satisfied at the root of the planning graph) and Goal_2 first
        appears in level 3, then the levelsum is 0 + 3 = 3.

        Hints
        -----
          (1) See the pseudocode folder for help on a simple implementation
          (2) You can implement this function more efficiently than the
              sample pseudocode if you expand the graph one level at a time
              and accumulate the level cost of each goal rather than filling
              the whole graph at the start.

        See Also
        --------
        Russell-Norvig 10.3.1 (3rd Edition)
        """
        # DONE: implement this function
        return sum(self._level_costs())

    def h_maxlevel(self):
        """ Calculate the max level heuristic for the planning graph

        The max level is the largest level cost of any single goal fluent.
        The "level cost" to achieve any single goal literal is the level at
        which the literal first appears in the planning graph. Note that
        the level cost is **NOT** the minimum number of actions to achieve
        a single goal literal.

        For example, if Goal1 first appears in level 1 of the graph and
        Goal2 first appears in level 3, then the levelsum is max(1, 3) = 3.

        Hints
        -----
          (1) See the pseudocode folder for help on a simple implementation
          (2) You can implement this function more efficiently if you expand
              the graph one level at a time until the last goal is met rather
              than filling the whole graph at the start.

        See Also
        --------
        Russell-Norvig 10.3.1 (3rd Edition)

        Notes
        -----
        WARNING: you should expect long runtimes using this heuristic with A*
        """
        # DONE: implement maxlevel heuristic
        return max(self._level_costs())

    @lru_cache(None)
    def h_setlevel(self):
        """ Calculate the set level heuristic for the planning graph

        The set level of a planning graph is the first level where all goals
        appear such that no pair of goal literals are mutex in the last
        layer of the planning graph.

        Hints
        -----
          (1) See the pseudocode folder for help on a simple implementation
          (2) You can implement this function more efficiently if you expand
              the graph one level at a time until you find the set level rather
              than filling the whole graph at the start.

        See Also
        --------
        Russell-Norvig 10.3.1 (3rd Edition)

        Notes
        -----
        WARNING: you should expect long runtimes using this heuristic on complex problems
        """
        # DONE: implement setlevel heuristic
        level = self.h_maxlevel()
        while not self._is_leveled:
            if not any(self.literal_layers[level].is_mutex(goalA, goalB)
                       for goalA, goalB in combinations(self.goal, 2)):
                return level
            self._extend()
            level += 1
        raise Exception("Planning graph doesn't contain a possible solution for the set of goals: %s" % self.goal)

    ##############################################################################
    #                     DO NOT MODIFY CODE BELOW THIS LINE                     #
    ##############################################################################

    def fill(self, maxlevels=-1):
        """ Extend the planning graph until it is leveled, or until a specified number of
        levels have been added

        Parameters
        ----------
        maxlevels : int
            The maximum number of levels to extend before breaking the loop. (Starting with
            a negative value will never interrupt the loop.)

        Notes
        -----
        YOU SHOULD NOT THIS FUNCTION TO COMPLETE THE PROJECT, BUT IT MAY BE USEFUL FOR TESTING
        """
        while not self._is_leveled:
            if maxlevels == 0: break
            self._extend()
            maxlevels -= 1
        return self

    def _extend(self):
        """ Extend the planning graph by adding both a new action layer and a new literal layer

        The new action layer contains all actions that could be taken given the positive AND
        negative literals in the leaf nodes of the parent literal level.

        The new literal layer contains all literals that could result from taking each possible
        action in the NEW action layer. 
        """
        if self._is_leveled: return

        parent_literals = self.literal_layers[-1]
        parent_actions = parent_literals.parent_layer
        action_layer = ActionLayer(parent_actions, parent_literals, self._serialize, self._ignore_mutexes)
        literal_layer = LiteralLayer(parent_literals, action_layer, self._ignore_mutexes)

        for action in self._actionNodes:
            # actions in the parent layer are skipped because are added monotonically to planning graphs,
            # which is performed automatically in the ActionLayer and LiteralLayer constructors
            if action not in parent_actions and action.preconditions <= parent_literals:
                action_layer.add(action)
                literal_layer |= action.effects

                # add two-way edges in the graph connecting the parent layer with the new action
                parent_literals.add_outbound_edges(action, action.preconditions)
                action_layer.add_inbound_edges(action, action.preconditions)

                # # add two-way edges in the graph connecting the new literaly layer with the new action
                action_layer.add_outbound_edges(action, action.effects)
                literal_layer.add_inbound_edges(action, action.effects)

        action_layer.update_mutexes()
        literal_layer.update_mutexes()
        self.action_layers.append(action_layer)
        self.literal_layers.append(literal_layer)
        self._is_leveled = literal_layer == action_layer.parent_layer
