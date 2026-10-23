from __future__ import annotations

import io
import unittest

from tools.qualify_harness_bridge import check_fixture, qualified_coverage, run_suite


class QualificationGuardsTests(unittest.TestCase):
    def test_fixture_requires_exact_revision_hashes_and_clean_checkout(self):
        sources = {
            'local_execution_lease.py': 'fcbc7b571f6033ea64b584468bd16e198e59abeb162fb8fbffb02bcba14b16d9',
            'local_execution_lease_state.py': '1e19380e036ad1b622b3aebce82c3cc6b97e2008bdaf0e382b0367dabffe94e2',
        }
        public = '9d88a091a56e9a5fb76c3c901a1da75b01c5c110'
        check_fixture(public, sources, False)
        check_fixture('d7640a03b4b823d960f6e382607ad04aa8678c84', sources, False)
        for revision, hashes, dirty in (
            ('a' * 40, sources, False),
            (public, {**sources, 'local_execution_lease.py': 'b' * 64}, False),
            (public, sources, True),
        ):
            with self.assertRaises(RuntimeError):
                check_fixture(revision, hashes, dirty)
        self.assertTrue(qualified_coverage(19, 19))
        self.assertFalse(qualified_coverage(18, 20))
        self.assertFalse(qualified_coverage(20, 18))

    def test_only_executed_non_skipped_passing_tests_qualify(self):
        class Probe(unittest.TestCase):
            def test_pass(self):
                pass

            @unittest.skip('deliberate guard probe')
            def test_skip(self):
                pass

            def test_fail(self):
                self.fail('deliberate guard probe')

            def test_error(self):
                raise RuntimeError('deliberate guard probe')

        for method, expected in ((None, False), ('test_pass', True), ('test_skip', False),
                                 ('test_fail', False), ('test_error', False)):
            with self.subTest(method=method):
                suite = unittest.TestSuite([] if method is None else [Probe(method)])
                report = run_suite(suite, stream=io.StringIO())
                self.assertIs(report['qualified'], expected)
                self.assertEqual(0 if method is None else 1, report['tests_run'])
                self.assertEqual(1 if method == 'test_skip' else 0, report['skipped'])
                self.assertEqual(1 if method == 'test_fail' else 0, report['failures'])
                self.assertEqual(1 if method == 'test_error' else 0, report['errors'])
