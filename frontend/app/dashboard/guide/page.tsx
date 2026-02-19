import Link from "next/link";
import { Button } from "../../_components/ui/Button";
import { Card, CardContent } from "../../_components/ui/Card";
import { PageHeader } from "../../_components/PageHeader";

export default function DashboardGuidePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard Guide"
        description="Learn how to use the strategy dashboard and understand key metrics"
        right={
          <Link href="/dashboard">
            <Button size="sm" variant="outline">
              Back to Dashboard
            </Button>
          </Link>
        }
      />

      <Card className="shadow-none">
        <CardContent className="space-y-4 py-6">
          <div>
            <h2 className="mb-2">What is this Dashboard?</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">
              This dashboard tracks the historical performance of trading strategies based on public data sources like congressional
              trades, lobbying disclosures, and hedge fund filings (13F forms). Each strategy replicates what would have happened if
              you followed the disclosed trades.
            </p>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Quick Start (3 steps)</h2>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  1
                </div>
                <div>
                  <div className="text-sm font-semibold">Pick a preset</div>
                  <div className="text-sm text-muted-foreground">
                    Click a preset button like &quot;Top 5 CAGR&quot; or &quot;Congress&quot; to instantly see the best-performing strategies.
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  2
                </div>
                <div>
                  <div className="text-sm font-semibold">Compare on the chart</div>
                  <div className="text-sm text-muted-foreground">
                    The chart shows how $100 invested in each strategy would have grown over time. The dashed line is the S&P 500
                    benchmark.
                  </div>
                </div>
              </div>
              <div className="flex gap-3">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  3
                </div>
                <div>
                  <div className="text-sm font-semibold">Run a custom backtest (optional)</div>
                  <div className="text-sm text-muted-foreground">
                    Use the Backtest Wizard to test your own combination of strategies with custom weights and date ranges.
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Key Metrics Explained</h2>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border bg-muted/30 p-3">
                <div className="mb-1 text-sm font-semibold">CAGR (Compound Annual Growth Rate)</div>
                <div className="text-sm text-muted-foreground">
                  The average yearly return percentage. Example: 15% CAGR means your investment grew by 15% per year on average.
                  Higher is better.
                </div>
              </div>
              <div className="rounded-lg border bg-muted/30 p-3">
                <div className="mb-1 text-sm font-semibold">Sharpe Ratio</div>
                <div className="text-sm text-muted-foreground">
                  Measures risk-adjusted returns. Higher is better. Above 1.0 is good, above 2.0 is excellent. It tells you how much
                  return you got per unit of risk taken.
                </div>
              </div>
              <div className="rounded-lg border bg-muted/30 p-3">
                <div className="mb-1 text-sm font-semibold">Max Drawdown</div>
                <div className="text-sm text-muted-foreground">
                  The largest peak-to-trough decline. Example: -30% means at some point, the strategy lost 30% from its highest
                  value. Smaller (less negative) is better.
                </div>
              </div>
              <div className="rounded-lg border bg-muted/30 p-3">
                <div className="mb-1 text-sm font-semibold">SPY Benchmark</div>
                <div className="text-sm text-muted-foreground">
                  The S&P 500 ETF, representing the overall U.S. stock market. We compare all strategies against this to see if they
                  beat the market.
                </div>
              </div>
            </div>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Strategy Categories</h2>
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-sm font-semibold">Congressional Strategies</div>
                <div className="text-sm text-muted-foreground">
                  Based on stock trades disclosed by members of Congress (House and Senate). Examples: &quot;Congress Buys&quot;, &quot;U.S. House
                  Long-Short&quot;, committee-specific strategies.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Individual Politicians</div>
                <div className="text-sm text-muted-foreground">
                  Tracks specific politicians known for active trading. Examples: Nancy Pelosi, Dan Meuser, Josh Gottheimer.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Lobbying & Contracts</div>
                <div className="text-sm text-muted-foreground">
                  Companies with high lobbying spending or government contracts. Examples: &quot;Top Lobbying Spenders&quot;, &quot;Top Gov Contract
                  Recipients&quot;.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">13F Hedge Funds</div>
                <div className="text-sm text-muted-foreground">
                  Follows quarterly filings from famous hedge fund managers. Examples: Michael Burry, Bill Ackman, Howard Marks, Bill
                  Gates.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Insider Trading</div>
                <div className="text-sm text-muted-foreground">
                  Corporate insider purchases (legal disclosures when executives buy their own company stock).
                </div>
              </div>
            </div>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Chart Modes</h2>
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-sm font-semibold">Compare to S&P 500 (recommended)</div>
                <div className="text-sm text-muted-foreground">
                  Each strategy starts at the same value as SPY on its first date. This makes it easy to see which strategies
                  outperformed the market.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Normalize to 100</div>
                <div className="text-sm text-muted-foreground">
                  All strategies start at 100, making it easier to compare relative growth rates when strategies started at different
                  times.
                </div>
              </div>
            </div>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Backtest Wizard (Advanced)</h2>
            <div className="space-y-3">
              <div className="text-sm text-muted-foreground">
                The Backtest Wizard lets you test custom combinations of strategies with specific weights and date ranges.
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Blend Returns (nav_blend)</div>
                <div className="text-sm text-muted-foreground">
                  Recommended for most users. Combines the equity curves of multiple strategies by their weights. Simple and intuitive.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Combine Holdings (holdings_union)</div>
                <div className="text-sm text-muted-foreground">
                  Advanced mode. Merges the actual holdings from all strategies and rebalances them together. More realistic but
                  complex.
                </div>
              </div>
              <div>
                <div className="mb-1 text-sm font-semibold">Transaction Costs</div>
                <div className="text-sm text-muted-foreground">
                  Measured in basis points (bps). 1 bps = 0.01%. Example: 10 bps = 0.1% cost per trade. Set to 0 for idealized
                  backtests.
                </div>
              </div>
            </div>
          </div>

          <div className="border-t pt-4">
            <h2 className="mb-3">Tips</h2>
            <ul className="list-inside list-disc space-y-2 text-sm text-muted-foreground">
              <li>Start with &quot;Top 5 CAGR&quot; to see the best historical performers</li>
              <li>Compare Congress vs individual politicians to see who performed best</li>
              <li>Use the filter box to search for specific strategies by name</li>
              <li>Click multiple strategies to overlay them on the chart</li>
              <li>Check the stats cards to see average performance across your selection</li>
              <li>If a strategy is &quot;enabled but missing curves&quot;, click &quot;Update Strategy Data&quot; to generate it</li>
            </ul>
          </div>

          <div className="border-t pt-4">
            <div className="rounded-lg bg-muted/50 p-4">
              <div className="mb-2 text-sm font-semibold">Need more help?</div>
              <div className="text-sm text-muted-foreground">
                Hover over the small &quot;?&quot; icons throughout the dashboard for quick explanations. Check the Strategies page to
                enable/disable specific strategies, or visit Portfolios to create reusable strategy combinations.
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
