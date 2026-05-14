"use client";

import { useMemo } from "react";
import {
  BarController,
  BarElement,
  Chart as ChartJS,
  Legend,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  TimeScale,
  Tooltip,
} from "chart.js";
import "chartjs-adapter-date-fns";
import { Chart } from "react-chartjs-2";
import { useTheme } from "../_components/theme";

ChartJS.register(LineController, BarController, LineElement, BarElement, LinearScale, PointElement, TimeScale, Tooltip, Legend);

type Daily = { date: string; equity: number; daily_pnl: number };

export function PaperPerformanceCharts(props: { daily: Daily[] }) {
  const { theme } = useTheme();
  const { daily } = props;

  const chartData = useMemo(() => {
    const eq = daily.map((d) => ({ x: d.date, y: d.equity }));
    const bars = daily.slice(1).map((d) => ({ x: d.date, y: d.daily_pnl }));
    return {
      datasets: [
        {
          type: "line" as const,
          label: "Equity",
          data: eq,
          borderColor: "#7aa2f7",
          backgroundColor: "transparent",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.15,
          yAxisID: "y",
        },
        {
          type: "bar" as const,
          label: "Daily P&L",
          data: bars,
          backgroundColor: bars.map((b) => (b.y >= 0 ? "rgba(52, 211, 153, 0.55)" : "rgba(248, 113, 113, 0.55)")),
          yAxisID: "y1",
        },
      ],
    };
  }, [daily]);

  const options = useMemo(() => {
    const isDark = theme === "dark";
    const grid = isDark ? "rgba(148,163,184,0.18)" : "rgba(15,23,42,0.12)";
    const tick = isDark ? "rgba(226,232,240,0.92)" : "rgba(30,41,59,0.9)";
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index" as const, intersect: false },
      plugins: {
        legend: { labels: { color: tick } },
        tooltip: {
          callbacks: {
            label(ctx: { dataset?: { label?: string }; parsed?: { y?: number } }) {
              const v = ctx.parsed?.y;
              if (v == null) return "";
              if (ctx.dataset?.label === "Equity") return `Equity: $${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
              return `Daily P&L: $${Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "time" as const,
          time: { unit: "day" as const, displayFormats: { day: "MMM d" } },
          ticks: { color: tick, maxRotation: 0 },
          grid: { color: grid },
        },
        y: {
          position: "left" as const,
          title: { display: true, text: "Equity ($)", color: tick },
          ticks: {
            color: tick,
            callback: (v: string | number) => `$${Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
          },
          grid: { color: grid },
        },
        y1: {
          position: "right" as const,
          title: { display: true, text: "Daily P&L ($)", color: tick },
          ticks: { color: tick },
          grid: { drawOnChartArea: false },
        },
      },
    };
  }, [theme]);

  if (daily.length < 2) {
    return <div className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">Not enough history for a chart yet.</div>;
  }

  return (
    <div className="h-[320px] w-full">
      <Chart type="line" data={chartData as never} options={options as never} />
    </div>
  );
}
