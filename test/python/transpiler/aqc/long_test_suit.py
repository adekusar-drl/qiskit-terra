# This code is part of Qiskit.
#
# (C) Copyright IBM 2021.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
"""Long test suite"""

import os
import sys
import traceback

if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())
import unittest
from pprint import pprint

# TODO: remove this
# from contextlib import redirect_stdout
def redirect_to_file(text):
    original = sys.stdout
    sys.stdout = open("/path/to/redirect.txt", "w")
    print("This is your redirected text:")
    print(text)
    sys.stdout = original


if __name__ == "__main__":
    try:
        print("!!! Run this script from the project root folder !!!")
        print("Usage example:")
        print("python3 ./compilers/aqc_rc1/test/long_test_suit.py > test.txt 2>&1")
        print("\n\n")

        # Initialize the test suite.
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()

        # Add tests to the test suite.
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_cmp_cnot_struct))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_cnot_structures))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_parametric_circuit))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_compression))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_aqc))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.test_gradient_test))
        suite.addTests(loader.loadTestsFromModule(compilers.aqc_rc1.test.fast_gradient.test_utils))
        suite.addTests(
            loader.loadTestsFromModule(compilers.aqc_rc1.test.fast_gradient.test_layer1q)
        )
        suite.addTests(
            loader.loadTestsFromModule(compilers.aqc_rc1.test.fast_gradient.test_layer2q)
        )
        suite.addTests(
            loader.loadTestsFromModule(compilers.aqc_rc1.test.fast_gradient.test_cmp_gradients)
        )

        # Initialize a runner, pass it your suite and run it.
        log_file = "long_test_suit.log"
        print("Test's log will be recorded into {:s}".format(log_file))
        with open(log_file, "w+") as fd:
            runner = unittest.TextTestRunner(stream=fd, verbosity=1)
            result = runner.run(suite)
            print("Summary:")
            pprint(result)
            assert result.wasSuccessful(), "test failed"
    except Exception as ex:
        print("message length:", len(str(ex)))
        traceback.print_exc()