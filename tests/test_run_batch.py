import unittest

import run_batch


class RunBatchTest(unittest.TestCase):
    def test_default_batch_covers_both_thesis_demonstrators(self) -> None:
        geometry_keys = {geometry.key for geometry in run_batch.GEOMETRIES}
        self.assertEqual({"simulation_03", "simulation_04"}, geometry_keys)

    def test_extract_summary_metrics_exports_percentage_band_columns(self) -> None:
        run_metrics = {
            "K": {
                "structural_metrics": {
                    "original": {
                        "bandwidth": 10,
                        "avg_bandwidth": 2.5,
                        "nnz": 20,
                        "frac_within_|i-j|<=0.1%_of_n": 0.1,
                        "frac_within_|i-j|<=0.4%_of_n": 0.2,
                        "frac_within_|i-j|<=0.7%_of_n": 0.3,
                        "frac_within_|i-j|<=1.0%_of_n": 0.4,
                    },
                    "permuted": {
                        "bandwidth": 8,
                        "avg_bandwidth": 2.0,
                        "nnz": 20,
                        "frac_within_|i-j|<=0.1%_of_n": 0.5,
                        "frac_within_|i-j|<=0.4%_of_n": 0.6,
                        "frac_within_|i-j|<=0.7%_of_n": 0.7,
                        "frac_within_|i-j|<=1.0%_of_n": 0.8,
                    },
                },
                "permutation_check": {
                    "mismatches": 0,
                    "max_abs_err": 0.0,
                },
            }
        }

        summary = run_batch._extract_summary_metrics(run_metrics, "K")

        self.assertEqual(0.1, summary["K_frac_0_1pct_original"])
        self.assertEqual(0.8, summary["K_frac_1_0pct_permuted"])
        self.assertNotIn("K_frac_within_200_original", summary)


if __name__ == "__main__":
    unittest.main()