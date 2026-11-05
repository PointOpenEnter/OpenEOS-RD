"""
Standalone Test Runner for OpenEOS Phase A & Phase B Verification Suite.
Executes all test cases offline and outputs a structured execution report.
"""

import sys
import os
import unittest
import time

# Ensure workspace root is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from tests.test_phase_a_decoders import TestPhaseADecoders
from tests.test_phase_a_payloads import TestPhaseAPayloads
from tests.test_phase_b_protocol_guard import TestPhaseBProtocolGuard
from tests.test_phase_b_transport_mock import TestPhaseBTransport
from tests.test_phase_b_protected_transport import TestProtectedUsbPtpTransportPipeline


def run_test_suite() -> int:
    """Executes all Phase A and Phase B test cases."""
    print("=" * 80)
    print(" OPENEOS VERIFICATION TEST SUITE (PHASE A & PHASE B)")
    print(" Engineering Directives: Pure Offline, Zero Wire I/O, Protocol Guard Check")
    print("=" * 80)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPhaseADecoders))
    suite.addTests(loader.loadTestsFromTestCase(TestPhaseAPayloads))
    suite.addTests(loader.loadTestsFromTestCase(TestPhaseBProtocolGuard))
    suite.addTests(loader.loadTestsFromTestCase(TestPhaseBTransport))
    suite.addTests(loader.loadTestsFromTestCase(TestProtectedUsbPtpTransportPipeline))

    start_time = time.time()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    elapsed = time.time() - start_time

    print("\n" + "=" * 80)
    print(f" EXECUTION SUMMARY:")
    print(f" Total Tests Executed: {result.testsRun}")
    print(f" Passed:               {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f" Failures:             {len(result.failures)}")
    print(f" Errors:               {len(result.errors)}")
    print(f" Total Elapsed Time:   {elapsed:.4f} s")
    print("=" * 80)

    if result.wasSuccessful():
        print(" >>> ALL PHASE A AND PHASE B TESTS PASSED (STATUS: VERIFIED) <<<")
        return 0
    else:
        print(" >>> TEST SUITE REPORTED FAILURES (STATUS: UNVERIFIED) <<<")
        return 1


if __name__ == "__main__":
    sys.exit(run_test_suite())
