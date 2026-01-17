import unittest

import numpy as np
import pandas as pd

from metrics_utils import period_return_from_equity, regression_vs_benchmark, win_loss_stats
from render_full_summary_html import render_markdown


class TestMetricsUtils(unittest.TestCase):
    def test_win_loss_stats(self):
        r = np.array([0.01, -0.02, 0.03, 0.0, -0.01])
        win_rate, avg_win, avg_loss = win_loss_stats(r)
        self.assertAlmostEqual(win_rate, 2 / 5)
        self.assertAlmostEqual(avg_win, (0.01 + 0.03) / 2)
        self.assertAlmostEqual(avg_loss, (-0.02 + -0.01) / 2)

    def test_period_return_from_equity(self):
        idx = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-02-15"])
        ec = pd.DataFrame({"portfolio_value": [100.0, 110.0, 121.0]}, index=idx)

        r1 = period_return_from_equity(ec, 1)
        self.assertAlmostEqual(r1, 121.0 / 110.0 - 1.0)

        r30 = period_return_from_equity(ec, 30)
        # 30 calendar days before 2025-02-15 is ~2025-01-16, last <= that is 2025-01-02 (110)
        self.assertAlmostEqual(r30, 121.0 / 110.0 - 1.0)

    def test_regression_vs_benchmark_linear_relation(self):
        # Construct returns where port_ex = 2 * bench_ex + constant (alpha_daily)
        dates = pd.date_range("2025-01-01", periods=60, freq="B")
        # Make benchmark vary so variance > 0.
        bench_vals = np.where((np.arange(len(dates)) % 2) == 0, 0.001, 0.002)
        bench = pd.Series(bench_vals, index=dates)
        port = pd.Series(2.0 * bench_vals, index=dates)  # beta ~2, alpha ~0 (when rf=0)

        stats = regression_vs_benchmark(port, bench, rf_annual=0.0)
        self.assertIsNotNone(stats.beta)
        self.assertAlmostEqual(stats.beta, 2.0, places=6)
        self.assertAlmostEqual(stats.alpha_annual or 0.0, 0.0, places=6)


class TestHtmlRenderer(unittest.TestCase):
    def test_render_markdown_table(self):
        md = "\n".join(
            [
                "### Title",
                "",
                "| A | B |",
                "|---|---:|",
                "| x | 1 |",
            ]
        )
        html_out = render_markdown(md)
        self.assertIn("<table>", html_out)
        self.assertIn("<th>A</th>", html_out)
        self.assertIn("<td>x</td>", html_out)


if __name__ == "__main__":
    unittest.main()

