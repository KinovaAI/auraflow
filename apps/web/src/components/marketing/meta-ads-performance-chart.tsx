"use client";

import { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MetaDailyPerformance } from "@/lib/meta-ads-api";

interface Props {
  data: MetaDailyPerformance[];
}

type Metric = "clicks" | "reach" | "conversions" | "spend_cents" | "roas" | "frequency";

const metricConfig: Record<
  Metric,
  { label: string; color: string; formatter: (v: number) => string }
> = {
  clicks: {
    label: "Clicks",
    color: "#3B82F6",
    formatter: (v) => v.toLocaleString(),
  },
  reach: {
    label: "Reach",
    color: "#8B5CF6",
    formatter: (v) => v.toLocaleString(),
  },
  conversions: {
    label: "Conversions",
    color: "#10B981",
    formatter: (v) => v.toFixed(0),
  },
  spend_cents: {
    label: "Spend",
    color: "#EF4444",
    formatter: (v) => `$${(v / 100).toFixed(0)}`,
  },
  roas: {
    label: "ROAS",
    color: "#F59E0B",
    formatter: (v) => `${v.toFixed(1)}x`,
  },
  frequency: {
    label: "Frequency",
    color: "#EC4899",
    formatter: (v) => v.toFixed(1),
  },
};

export function MetaAdsPerformanceChart({ data }: Props) {
  const [activeMetrics, setActiveMetrics] = useState<Metric[]>([
    "clicks",
    "conversions",
  ]);

  const toggleMetric = (metric: Metric) => {
    setActiveMetrics((prev) =>
      prev.includes(metric)
        ? prev.filter((m) => m !== metric)
        : [...prev, metric]
    );
  };

  const chartData = data.map((d) => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Performance Trend</CardTitle>
          <div className="flex flex-wrap gap-2">
            {(Object.entries(metricConfig) as [Metric, (typeof metricConfig)[Metric]][]).map(
              ([key, cfg]) => (
                <button
                  key={key}
                  onClick={() => toggleMetric(key)}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                    activeMetrics.includes(key)
                      ? "text-white"
                      : "bg-gray-100 text-gray-500 hover:bg-gray-200"
                  }`}
                  style={
                    activeMetrics.includes(key)
                      ? { backgroundColor: cfg.color }
                      : undefined
                  }
                >
                  {cfg.label}
                </button>
              )
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                stroke="#9CA3AF"
              />
              <YAxis tick={{ fontSize: 12 }} stroke="#9CA3AF" />
              <Tooltip
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: "1px solid #E5E7EB",
                }}
              />
              {activeMetrics.map((metric) => (
                <Line
                  key={metric}
                  type="monotone"
                  dataKey={metric}
                  name={metricConfig[metric].label}
                  stroke={metricConfig[metric].color}
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
