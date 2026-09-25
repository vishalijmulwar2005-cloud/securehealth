"use client";
/** Minimal SVG charts in exact design tokens (the spec's "2D equivalent").
 * Dotted grid, mono labels, draw-in honoring reduced motion. Ported from the
 * verified console's charts.jsx. */

const GRID = "#EEF2F4";
const FAINT = "#7c8b99";
const MONO = "JetBrains Mono, ui-monospace, monospace";

function Frame({ width = 640, height = 220, children, yLabels = [], xLabels = [] }: {
  width?: number; height?: number; children: React.ReactNode;
  yLabels?: { x?: number; y: number; t: string }[]; xLabels?: { x: number; y?: number; t: string }[];
}) {
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto" role="img">
      {[0.15, 0.4, 0.65, 0.9].map((f, i) => (
        <line key={i} x1={44} x2={width - 12} y1={height * f} y2={height * f} stroke={GRID} strokeDasharray="2 4" />
      ))}
      {yLabels.map((l, i) => (
        <text key={`y${i}`} x={38} y={l.y + 4} textAnchor="end" fontSize={10} fill={FAINT} fontFamily={MONO}>{l.t}</text>
      ))}
      {xLabels.map((l, i) => (
        <text key={`x${i}`} x={l.x} y={l.y ?? height - 6} textAnchor="middle" fontSize={10} fill={FAINT} fontFamily={MONO}>{l.t}</text>
      ))}
      {children}
    </svg>
  );
}

export function LineChart({ series, height = 220 }: {
  series: { key: string; label: string; color: string; data: { x: string; y: number }[] }[]; height?: number }) {
  const W = 640, H = height, X0 = 44, X1 = W - 12, Y0 = 12, Y1 = H - 28;
  const all = series.flatMap((s) => s.data.map((d) => d.y));
  const max = Math.max(1, ...all);
  const min = Math.min(0, ...all);
  const px = (i: number, n: number) => (n <= 1 ? (X0 + X1) / 2 : X0 + (i * (X1 - X0)) / (n - 1));
  const py = (v: number) => Y1 - ((v - min) / (max - min || 1)) * (Y1 - Y0);
  const n = Math.max(...series.map((s) => s.data.length), 1);
  return (
    <Frame width={W} height={H}
      yLabels={[0, 1, 2, 3].map((i) => ({ y: Y0 + (i * (Y1 - Y0)) / 3, t: (max - (i * (max - min)) / 3).toFixed(2) }))}
      xLabels={series[0]?.data.filter((_, i) => i % Math.ceil(n / 8) === 0 || i === n - 1)
        .map((d, k, arr) => ({ x: px(arr.indexOf(d) * Math.ceil(n / 8) || k * Math.ceil(n / 8), n), t: d.x })) || []}>
      {series.map((s) => {
        const pts = s.data.map((d, i) => `${px(i, s.data.length)},${py(d.y)}`).join(" ");
        return <polyline key={s.key} points={pts} fill="none" stroke={s.color} strokeWidth={2}
          className="chart-draw" style={{ ["--len" as string]: 1200 }} />;
      })}
      {series.map((s) => s.data.map((d, i) => (
        <circle key={`${s.key}-${i}`} cx={px(i, s.data.length)} cy={py(d.y)} r={2.5} fill={s.color}>
          <title>{`${s.label} - ${d.x}: ${d.y}`}</title>
        </circle>
      )))}
    </Frame>
  );
}

export function AreaChart({ data, color = "#0e7c7b", height = 180 }: {
  data: { x: string; y: number }[]; color?: string; height?: number }) {
  const W = 640, H = height, X0 = 44, X1 = W - 12, Y0 = 12, Y1 = H - 28;
  const max = Math.max(1, ...data.map((d) => d.y));
  const px = (i: number) => (data.length <= 1 ? (X0 + X1) / 2 : X0 + (i * (X1 - X0)) / (data.length - 1));
  const py = (v: number) => Y1 - (v / max) * (Y1 - Y0);
  const pts = data.map((d, i) => `${px(i)},${py(d.y)}`).join(" ");
  return (
    <Frame width={W} height={H}
      yLabels={[0, 1, 2].map((i) => ({ y: Y0 + (i * (Y1 - Y0)) / 2, t: (max - (i * max) / 2).toFixed(1) }))}
      xLabels={data.filter((_, i) => i % Math.ceil(data.length / 8) === 0 || i === data.length - 1)
        .map((d, i) => ({ x: px(data.indexOf(d) || i), t: d.x }))}>
      <polygon points={`${X0},${Y1} ${pts} ${X1},${Y1}`} fill={color} opacity={0.14} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth={2} className="chart-draw" style={{ ["--len" as string]: 900 }} />
    </Frame>
  );
}

export function GroupedBars({ groups, series, height = 240 }: {
  groups: string[]; series: { key: string; label: string; color: string; data: number[] }[]; height?: number }) {
  const W = 640, H = height, X0 = 44, X1 = W - 12, Y0 = 12, Y1 = H - 40;
  const max = Math.max(10, ...series.flatMap((s) => s.data));
  const gw = (X1 - X0) / groups.length;
  const bw = Math.min(22, (gw * 0.7) / series.length);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img">
      {[0, 1, 2].map((i) => (
        <line key={i} x1={X0} x2={X1} y1={Y0 + (i * (Y1 - Y0)) / 2} y2={Y0 + (i * (Y1 - Y0)) / 2} stroke={GRID} strokeDasharray="2 4" />
      ))}
      {[0, 1, 2].map((i) => (
        <text key={`t${i}`} x={X0 - 6} y={Y0 + (i * (Y1 - Y0)) / 2 + 4} textAnchor="end" fontSize={10} fill={FAINT} fontFamily={MONO}>
          {(max - (i * max) / 2).toFixed(0)}%
        </text>
      ))}
      {groups.map((g, gi) => {
        const gx = X0 + gi * gw;
        return (
          <g key={g}>
            {series.map((s, si) => {
              const v = s.data[gi];
              const h = (v / max) * (Y1 - Y0);
              const x = gx + (gw - bw * series.length) / 2 + si * bw;
              return (
                <rect key={s.key} x={x} y={Y1 - h} width={bw - 3} height={h} rx={2} fill={s.color} opacity={0.85}>
                  <title>{`${g} - ${s.label}: ${v}%`}</title>
                </rect>
              );
            })}
            <text x={gx + gw / 2} y={H - 22} textAnchor="middle" fontSize={11} fontWeight={600} fill="#14263b">{g}</text>
          </g>
        );
      })}
    </svg>
  );
}
