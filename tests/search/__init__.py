"""Search adapter and service tests."""

import unittest


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str,
) -> unittest.TestSuite:
    del loader, tests, pattern
    return unittest.TestSuite()
