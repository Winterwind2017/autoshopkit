"""Run each script-style suite through pytest.

The suites are written as ``main()`` scripts so they can also be run directly
(``python tests/test_hcp.py``); a suite that needs data or a live AutoShop session
returns 0 after printing SKIP lines, so this stays green on a clean machine.
"""

import importlib
import sys

import pytest

SUITES = [
    "test_ilparse",
    "test_projectfile",
    "test_hcp",
    "test_h5u_il",
    "test_ladder",
    "test_offline_audit",
]


@pytest.mark.parametrize("name", SUITES)
def test_suite(name):
    module = importlib.import_module(name)
    assert module.main() == 0
