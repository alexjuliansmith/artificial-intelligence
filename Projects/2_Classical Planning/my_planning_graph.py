
from itertools import chain, combinations
from functools import lru_cache
from aimacode.utils import Expr
from collections import defaultdict
from layers import BaseLayer, makeNoOp, make_node, ActionNode


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

#############################################################################
class FastBaseLayer(BaseLayer):
    def __init__(self, grandparent_layer=[], parent_layer=None, ignore_mutexes=False):
        super().__init__(grandparent_layer, parent_layer, ignore_mutexes)
        self._new_items = set()
        self._items_relaxed = set()
        if isinstance(grandparent_layer, BaseLayer):
            self._mutexes = grandparent_layer._mutexes
            self._mutex_vector = grandparent_layer._mutex_vector.copy()
        else:
            self._mutex_vector = defaultdict(int)

    def __eq__(self, other):
        return (len(self) == len(other) and
                len(self._mutex_vector) == len(other._mutex_vector) and
                not(self ^ other) and
                self._mutex_vector == other._mutex_vector)

    def add(self, item):
        if item not in self:
            self._new_items.add(item)
            super().add(item)

    def is_mutex(self, itemA, itemB):
        return itemA.index & self._mutex_vector[itemB]

    def set_mutex(self, itemA, itemB):
#        assert itemA not in self._mutexes[itemB] and itemB not in self._mutexes[itemA], "{} in {}\nor\n{} in {}".format(itemA, self._mutexes[itemB], itemB, self._mutexes[itemA])

        super().set_mutex(itemA, itemB)
        self.set_mutex_vector(itemA, itemB)

        assert itemA in self._mutexes[itemB] and itemB in self._mutexes[itemA]

    def set_static_mutex(self, itemA, itemB):
        self.set_mutex_vector(itemA, itemB)

    def set_mutex_vector(self, itemA, itemB):
        assert itemA != itemB
#        assert self._mutex_vector[itemA] & itemB.index == self._mutex_vector[itemB] & itemA.index == 0

        self._mutex_vector[itemA] |= itemB.index
        self._mutex_vector[itemB] |= itemA.index

        assert self._mutex_vector[itemA] & itemB.index == itemB.index and self._mutex_vector[itemB] & itemA.index == itemA.index

    def relax_mutex(self, itemA, itemB):
        assert itemA != itemB
        assert itemA in self._mutexes[itemB] and itemB in self._mutexes[itemA]
        assert self._mutex_vector[itemA] & itemB.index == itemB.index and self._mutex_vector[itemB] & itemA.index == itemA.index

        self._mutexes[itemA].remove(itemB)
        self._mutexes[itemB].remove(itemA)
        self._mutex_vector[itemA] ^= itemB.index
        self._mutex_vector[itemB] ^= itemA.index

        assert itemA not in self._mutexes[itemB] and itemB not in self._mutexes[itemA]
        assert self._mutex_vector[itemA] & itemB.index == self._mutex_vector[itemB] & itemA.index == 0



    def add_outbound_edges(self, action, literals):
        pass

    def update_mutexes(self):
        if not self._ignore_mutexes:
            # Recheck all temporary mutexes from previous layer, relax if not still mutex
            for itemA in self._mutexes:
                relaxations = []
                for itemB in self._mutexes[itemA]:
                    if not self.is_temporary_mutex(itemA, itemB):
                        relaxations.append(itemB)
                for itemB in relaxations:
                    self.relax_mutex(itemA, itemB)
        # Test items newly added in this layer against all items to find any new mutexes
        for itemA in self._new_items:
            for itemB in self:
                if itemA != itemB:
                    if self.is_static_mutex(itemA, itemB):
                        self.set_static_mutex(itemA, itemB)
                    elif not self._ignore_mutexes and self.is_temporary_mutex(itemA, itemB):
                        self.set_mutex(itemA, itemB)

##############################################################################

class FastLiteralNode(Expr):
    __slots__ = ['index', '__negation']
    def __init__(self, op, *args):
        super().__init__(op, *args)
        self.index = literal_index(self)
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
            self.preconditions_vector |= p.index
        for e in self.effects:
            self.effects_vector |= e.index
            self.negated_effects_vector |= (~e).index

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
Expr.index = property(lambda self : literal_index(self))

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


class ActionLayer(FastBaseLayer):

    def __init__(self, actions=[], parent_layer=None, serialize=True, ignore_mutexes=False):
        super().__init__(actions, parent_layer, ignore_mutexes)
        self._serialize = serialize



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
        try:
            actionB_precondition_mutexes = 0
            for precondB in actionB.preconditions: #TODO cache this
                actionB_precondition_mutexes |= self.parent_layer._mutex_vector[precondB]
            return actionA.preconditions_vector & actionB_precondition_mutexes
        except AttributeError:
            # raise AttributeError("Should only occur on test 4")
            # This branch necessary to pass some Test_4_CompetingNeedsMutex unittests which build their own ActionNode
            return any(self.parent_layer.is_mutex(precondA, precondB)
                       for precondA in actionA.preconditions for precondB in actionB.preconditions)

    ################  Add Faster implementation

    def add_inbound_edges(self, action, literals):
        pass

    def is_static_mutex(self, actionA, actionB):
        return (self._serialize and actionA.no_op == actionB.no_op == False) \
            or self._interference(actionA, actionB) \
            or self._inconsistent_effects(actionA, actionB) \

    def is_temporary_mutex(self, actionA, actionB):
            return self._competing_needs(actionA, actionB)

    def relax_mutex(self, actionA, actionB):
        super().relax_mutex(actionA, actionB)
        self._items_relaxed |= actionA.effects | actionB.effects

    def update_mutexes(self):
        if not self._ignore_mutexes:
            # Recheck all temporary mutexes from previous layer, relax if not still mutex
            possible_actions_to_relax = self.parent_layer._items_relaxed
            while possible_actions_to_relax:
                itemA = possible_actions_to_relax.pop()
                relaxations = []
                for itemB in self._mutexes[itemA]:
                    if itemB in possible_actions_to_relax and not self.is_temporary_mutex(itemA, itemB):
                        relaxations.append(itemB)
                for itemB in relaxations:
                    self.relax_mutex(itemA, itemB)
        # Test items newly added in this layer against all items to find any new mutexes
        for itemA in self._new_items:
            for itemB in self:
                if itemA != itemB:
                    if self.is_static_mutex(itemA, itemB):
                        self.set_static_mutex(itemA, itemB)
                    elif not self._ignore_mutexes and self.is_temporary_mutex(itemA, itemB):
                        self.set_mutex(itemA, itemB)



class LiteralLayer(FastBaseLayer):

    def __init__(self, literals=[], parent_layer=None, ignore_mutexes=False):
        super().__init__(literals, parent_layer, ignore_mutexes)
        if isinstance(literals, LiteralLayer):
            self.parents.update({k: set(v) for k, v in literals.parents.items()})
            self.children = literals.children
        else:
            #TODO quick hack to get static mutexes in literal layer for Test4b
            for literal in iter(self):
                self._mutex_vector[literal] = (~literal).index


    def _inconsistent_support(self, literalA, literalB):
        """ Return True if all ways to achieve both literals are pairwise mutex in the parent layer

        Hints:
            (1) `self.parent_layer` contains a reference to the previous action layer
            (2) `self.parents` contains a map from literals to actions in the parent layer

        See Also
        --------
        layers.BaseLayer.parent_layer
        """
        # DONE: implement this function
        causes_A, causes_B = self.parents[literalA], self.parents[literalB]
        #return all(self.parent_layer.is_mutex(causeA, causeB) for causeA in causes_A for causeB in causes_B)
        #TODO cache vectors in layer
        causes_A_vector  = 0
        for causeA in causes_A:
            causes_A_vector |= causeA.index
        causes_B_mutex_vector = causes_A_vector
        for causeB in causes_B:
            causes_B_mutex_vector &= self.parent_layer._mutex_vector[causeB]
        return causes_B_mutex_vector == causes_A_vector


    def _negation(self, literalA, literalB):
        """ Return True if two literals are negations of each other """
        # DONE: implement this function
        return literalA == ~literalB

    ################  Add Faster implementation

    def add_inbound_edges(self, action, literals):
    # inbound literal edges are many-to-many
        for literal in literals:
            self.parents[literal].add(action)

    def add_outbound_edges(self, action, literals):
        # outbound literal edges are many-to-many
        for literal in literals:
            self.children[literal].add(action)

    def is_static_mutex(self, literalA, literalB):
        return self._negation(literalA, literalB)

    def is_temporary_mutex(self, literalA, literalB):
        return self._inconsistent_support(literalA, literalB)

    def relax_mutex(self, literalA, literalB):
        super().relax_mutex(literalA, literalB)
        self._items_relaxed |= self.children[literalA] | self.children[literalB]


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
