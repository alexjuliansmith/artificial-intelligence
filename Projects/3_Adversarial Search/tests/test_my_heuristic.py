
import unittest

from collections import deque
from random import choice
from textwrap import dedent

from isolation import Isolation, Agent, fork_get_action, play
from sample_players import RandomPlayer
from my_custom_player import *




class BaseCustomHeuristicTest(unittest.TestCase):
    def setUp(self):
        self.MID = 57   #Assuming 11 by 9 board
        self.knight_start  = 1 << self.MID



class CustomPlayerGetActionTest(BaseCustomHeuristicTest):

    def test_get_knights(self):
        """ get knights moves wavefronts fill an empty bpard from centre as expected """
        knights = self.knight_start
        booard_ids = [41523161179755588175928227572738047,
                      38114874426268006157864658273658711,
                      13835983132169903245103409681572522,
                      27687178071769218837580222542726485,
                      13835983132169903245103409681572522]

        for i in range(5):
            #moves = get_knight_moves(knights, isolation._BLANK_BOARD)
            moves = get_all_knight_moves(knights, isolation._BLANK_BOARD)
            photo_negative = moves ^ BOARD_MASK
            self.assertEqual(photo_negative, booard_ids[i])

            knights = moves