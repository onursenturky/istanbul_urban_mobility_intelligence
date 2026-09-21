"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { semanticColors } from "@/lib/theme";

export interface ChartCardProps {
  title: string;
  question: string;
  data: Array<Record<string, string | number>>;
  xKey: string;
  yKey: string;
  yLabel?: string;
  color?: string;
  interpretationWarning?: string;
}

export function ChartCard({ title, question, data, xKey, yKey, yLabel, color = semanticColors.gain, interpretationWarning }: ChartCardProps) {
  return (
    <div className="rounded-2xl border border-o3-card bg-o3-card p-5">
      <h4 className="text-o3-text-primary font-semibold text-sm">{title}</h4>
      <p className="text-o3-text-secondary text-xs mt-0.5 mb-3">{question}</p>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(197,223,201,0.12)" vertical={false} />
            <XAxis dataKey={xKey} tick={{ fill: "#C5DFC9", fontSize: 11 }} axisLine={{ stroke: "rgba(197,223,201,0.2)" }} tickLine={false} />
            <YAxis tick={{ fill: "#C5DFC9", fontSize: 11 }} axisLine={false} tickLine={false} label={yLabel ? { value: yLabel, angle: -90, fill: "#C5DFC9", fontSize: 11, position: "insideLeft" } : undefined} />
            <Tooltip
              contentStyle={{ background: "#194B0A", border: "1px solid rgba(197,223,201,0.2)", borderRadius: 8, color: "#F1FFE0" }}
              labelStyle={{ color: "#F1FFE0" }}
              cursor={{ fill: "rgba(255,255,255,0.05)" }}
            />
            <Bar dataKey={yKey} fill={color} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {interpretationWarning && <p className="text-o3-text-secondary/80 text-[11px] mt-2 italic">{interpretationWarning}</p>}
    </div>
  );
}
