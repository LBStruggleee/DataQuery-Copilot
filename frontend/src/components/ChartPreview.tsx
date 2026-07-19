import type { QueryResponse } from "../types";

type Props = { result: QueryResponse };

const chartColors = ["#7c86e8", "#55b993", "#d7a55c", "#9b83d4", "#5d8ca8", "#b66f7e"];

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value.replace(/[^0-9.-]/g, ""));
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function getChartFields(result: QueryResponse) {
  const numericColumns = result.columns.filter((column) =>
    result.rows.some((row) => numberValue(row[column]) !== null),
  );
  const labelColumn = result.columns.find((column) => !numericColumns.includes(column)) ?? result.columns[0];
  return { numericColumns, labelColumn };
}

function EmptyChart({ message }: { message: string }) {
  return <div className="chart-empty"><span>[ chart ]</span><strong>{message}</strong><p>当前结果仍可在“结果”标签中查看。</p></div>;
}

function BarChart({ result }: Props) {
  const { numericColumns, labelColumn } = getChartFields(result);
  const valueColumn = numericColumns.find((column) => column !== labelColumn);
  if (!labelColumn || !valueColumn) return <EmptyChart message="没有找到可绘制的分类与数值列" />;
  const items = result.rows.slice(0, 12).map((row) => ({
    label: String(row[labelColumn] ?? "未命名"),
    value: numberValue(row[valueColumn]) ?? 0,
  }));
  const max = Math.max(...items.map((item) => Math.abs(item.value)), 1);
  return (
    <div className="dynamic-bars" aria-label={`${labelColumn} 与 ${valueColumn} 柱状图`}>
      <div className="dynamic-bars__plot">
        {items.map((item, index) => (
          <div className="dynamic-bar" key={`${item.label}-${index}`}>
            <strong>{item.value.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}</strong>
            <div className="dynamic-bar__track"><i style={{ height: `${Math.max(Math.abs(item.value) / max * 100, 3)}%`, animationDelay: `${index * 55}ms` }} /></div>
            <span title={item.label}>{item.label}</span>
          </div>
        ))}
      </div>
      <div className="chart-caption"><span>{labelColumn}</span><strong>{valueColumn}</strong></div>
    </div>
  );
}

function LineChart({ result }: Props) {
  const { numericColumns, labelColumn } = getChartFields(result);
  const valueColumn = numericColumns.find((column) => column !== labelColumn);
  if (!labelColumn || !valueColumn || result.rows.length < 2) return <EmptyChart message="折线图至少需要两个数据点" />;
  const items = result.rows.slice(0, 24).map((row) => ({
    label: String(row[labelColumn] ?? ""),
    value: numberValue(row[valueColumn]) ?? 0,
  }));
  const values = items.map((item) => item.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = items.map((item, index) => {
    const x = 26 + index * (588 / Math.max(items.length - 1, 1));
    const y = 210 - ((item.value - min) / range) * 170;
    return { ...item, x, y };
  });
  return (
    <div className="line-chart">
      <svg viewBox="0 0 640 240" role="img" aria-label={`${labelColumn} 与 ${valueColumn} 折线图`}>
        <path className="line-chart__grid" d="M26 40H614M26 96H614M26 153H614M26 210H614" />
        <polyline points={points.map((point) => `${point.x},${point.y}`).join(" ")} />
        {points.map((point, index) => <circle key={`${point.label}-${index}`} cx={point.x} cy={point.y} r="4"><title>{point.label}: {point.value}</title></circle>)}
      </svg>
      <div className="chart-caption"><span>{labelColumn}</span><strong>{valueColumn}</strong></div>
    </div>
  );
}

function PieChart({ result }: Props) {
  const { numericColumns, labelColumn } = getChartFields(result);
  const valueColumn = numericColumns.find((column) => column !== labelColumn);
  if (!labelColumn) return <EmptyChart message="没有找到分类列" />;
  const rawItems = result.rows.slice(0, 6).map((row) => ({
    label: String(row[labelColumn] ?? "未命名"),
    value: valueColumn ? numberValue(row[valueColumn]) ?? 0 : 1,
  }));
  const total = rawItems.reduce((sum, item) => sum + Math.abs(item.value), 0) || 1;
  let cursor = 0;
  const stops = rawItems.map((item, index) => {
    const start = cursor;
    cursor += Math.abs(item.value) / total * 100;
    return `${chartColors[index % chartColors.length]} ${start}% ${cursor}%`;
  }).join(", ");
  return (
    <div className="pie-chart">
      <div className="pie-chart__ring" style={{ background: `conic-gradient(${stops})` }}><div><strong>{rawItems.length}</strong><span>个分类</span></div></div>
      <div className="pie-chart__legend">
        {rawItems.map((item, index) => <div key={`${item.label}-${index}`}><i style={{ background: chartColors[index % chartColors.length] }} /><span>{item.label}</span><strong>{(Math.abs(item.value) / total * 100).toFixed(1)}%</strong></div>)}
      </div>
    </div>
  );
}

function ScatterChart({ result }: Props) {
  const { numericColumns } = getChartFields(result);
  if (numericColumns.length < 2) return <EmptyChart message="散点图需要两个数值列" />;
  const [xColumn, yColumn] = numericColumns;
  const points = result.rows.slice(0, 80).map((row) => ({ x: numberValue(row[xColumn]) ?? 0, y: numberValue(row[yColumn]) ?? 0 }));
  const maxX = Math.max(...points.map((point) => point.x), 1);
  const maxY = Math.max(...points.map((point) => point.y), 1);
  return (
    <div className="scatter-chart">
      <svg viewBox="0 0 640 240" role="img" aria-label={`${xColumn} 与 ${yColumn} 散点图`}>
        <path className="line-chart__grid" d="M26 40H614M26 96H614M26 153H614M26 210H614M26 40V210M222 40V210M418 40V210M614 40V210" />
        {points.map((point, index) => <circle key={index} cx={26 + point.x / maxX * 588} cy={210 - point.y / maxY * 170} r="4"><title>{xColumn}: {point.x}, {yColumn}: {point.y}</title></circle>)}
      </svg>
      <div className="chart-caption"><span>{xColumn}</span><strong>{yColumn}</strong></div>
    </div>
  );
}

export function ChartPreview({ result }: Props) {
  if (!result.rows.length) return <EmptyChart message="查询没有返回可绘制的数据" />;
  if (result.chart_hint === "bar") return <BarChart result={result} />;
  if (result.chart_hint === "line") return <LineChart result={result} />;
  if (result.chart_hint === "pie") return <PieChart result={result} />;
  if (result.chart_hint === "scatter") return <ScatterChart result={result} />;
  return <EmptyChart message="当前数据结构更适合表格展示" />;
}
