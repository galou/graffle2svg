#!/usr/bin/env python3

import unittest

from tests import get_tests

if __name__ == '__main__':
    suite = get_tests
    unittest.main(defaultTest='suite')
