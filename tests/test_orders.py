import unittest

from orders import Catalog, OrderInputError, OrderNotFound


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.channels = {'A': [2, 1], 'B': [3, -1]}
        self.catalog.profile('R1', self.channels)

    def test_fixed_profile(self):
        self.assertEqual(self.catalog.profile('R1', {'B': (3, -1), 'A': (2, 1)}), 'R1')
        fields = [('T1', 'A', 0, 5), ('T2', 'B', 0, 4)]
        self.assertEqual(self.catalog.issue('morning', 'R1', fields), 'morning')
        self.channels['A'][0] = 99
        fields.reverse()
        self.catalog.profile('R2', {'A': (5, 1), 'B': (10, 0)})
        fixed = self.catalog.get_order('morning')
        self.assertEqual(fixed.profile.revision_id, 'R1')
        self.assertEqual((fixed.profile.for_channel('A').multiplier, fixed.profile.for_channel('A').offset), (2, 1))
        self.assertEqual([(ticket.ticket_id, ticket.ordinal) for ticket in fixed.tickets], [('T1', 0), ('T2', 1)])
        self.assertEqual(self.catalog.issue('morning', 'R1', list(reversed(fields))), 'morning')
        with self.assertRaises(OrderInputError):
            self.catalog.issue('morning', 'R2', fields)
        self.assertEqual(self.catalog.get_order('morning'), fixed)

    def test_profile_conflict(self):
        with self.assertRaises(OrderInputError):
            self.catalog.profile('R1', {'A': (5, 1), 'B': (3, -1)})
        self.catalog.issue('morning', 'R1', [('T1', 'A', 0, 5)])
        scale = self.catalog.get_order('morning').profile.for_channel('A')
        self.assertEqual((scale.multiplier, scale.offset), (2, 1))
        for value in (None, False, 1.0):
            with self.subTest(value=value):
                with self.assertRaises(OrderInputError):
                    self.catalog.profile('bad-profile', {'A': (2, 1), 'B': (2, value)})
                with self.assertRaises(OrderInputError):
                    self.catalog.issue('bad-order', 'bad-profile', [('T1', 'A', 0, 4)])
                with self.assertRaises(OrderNotFound):
                    self.catalog.get_order('bad-order')
        self.assertEqual(self.catalog.profile('bad-profile', {'A': (0, -1)}), 'bad-profile')

    def test_repeated_ticket(self):
        with self.assertRaisesRegex(OrderInputError, 'duplicate ticket ID'):
            self.catalog.issue('duplicate', 'R1', [('T1', 'A', 0, 5), ('T1', 'A', 1, 6)])
        with self.assertRaises(OrderNotFound):
            self.catalog.get_order('duplicate')

    def test_cross_channel_duplicate(self):
        with self.assertRaisesRegex(OrderInputError, 'duplicate ticket ID'):
            self.catalog.issue('duplicate', 'R1', [('T1', 'A', 0, 5), ('T1', 'B', 0, 4)])
        with self.assertRaises(OrderNotFound):
            self.catalog.get_order('duplicate')
        self.assertEqual(self.catalog.issue('duplicate', 'R1', [('T1', 'A', 0, 5)]), 'duplicate')

    def test_invalid_order_fields(self):
        cases = [
            ('R1', []),
            ('R1', [(f'T{index}', 'A', 0, 600) for index in range(9)]),
            ('R1', [('T1', 'A', -1, 5)]),
            ('R1', [('T1', 'A', 0, 601)]),
            ('R1', [('T1', 'A', 6, 5)]),
            ('R1', [('T1', 'A', False, 5)]),
            ('R1', [('T1', 'A', 0, 5.0)]),
            ('R1', [('T1', 'A', 0)]),
            ('R1', [('T1', 'A', 0, 5), ('T2', 'C', 0, 4)]),
            ('missing', [('T1', 'A', 0, 5)]),
            ('R1', [('  ', 'A', 0, 5)]),
        ]
        for revision, fields in cases:
            with self.subTest(revision=revision, fields=fields):
                with self.assertRaises(OrderInputError):
                    self.catalog.issue('invalid', revision, fields)
                with self.assertRaises(OrderNotFound):
                    self.catalog.get_order('invalid')
        fields = [('T1', 'A', 0, 0)] + [(f'T{index}', 'B', 600, 600) for index in range(2, 9)]
        self.catalog.issue('bounds', 'R1', fields)
        tickets = self.catalog.get_order('bounds').tickets
        self.assertEqual(len(tickets), 8)
        self.assertEqual([(tickets[0].opens_at, tickets[0].closes_at),
                          (tickets[-1].opens_at, tickets[-1].closes_at)], [(0, 0), (600, 600)])
