import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

const defaults = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function DatabaseIcon(props: IconProps) {
  return <svg {...defaults} {...props}><ellipse cx="12" cy="5" rx="7" ry="3" /><path d="M5 5v7c0 1.7 3.1 3 7 3s7-1.3 7-3V5" /><path d="M5 12v7c0 1.7 3.1 3 7 3s7-1.3 7-3v-7" /></svg>;
}

export function SparkIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="m12 3 1.2 4.1a5 5 0 0 0 3.4 3.4l4.1 1.2-4.1 1.2a5 5 0 0 0-3.4 3.4L12 20.4l-1.2-4.1a5 5 0 0 0-3.4-3.4l-4.1-1.2 4.1-1.2a5 5 0 0 0 3.4-3.4L12 3Z" /></svg>;
}

export function TableIcon(props: IconProps) {
  return <svg {...defaults} {...props}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M9 9v11" /></svg>;
}

export function ChartIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="M4 19V9m6 10V5m6 14v-7m4 7H2" /></svg>;
}

export function CodeIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="m8 9-3 3 3 3m8-6 3 3-3 3m-3-9-2 12" /></svg>;
}

export function ChevronIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="m9 18 6-6-6-6" /></svg>;
}

export function ArrowIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="M5 12h14m-5-5 5 5-5 5" /></svg>;
}

export function CopyIcon(props: IconProps) {
  return <svg {...defaults} {...props}><rect x="8" y="8" width="11" height="11" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></svg>;
}

export function GithubIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.3-.4 6.8-1.6 6.8-7.4A5.8 5.8 0 0 0 19.2 3 5.4 5.4 0 0 0 19 0s-1.2-.4-4 1.5a13.8 13.8 0 0 0-7 0C5.2-.4 4 0 4 0a5.4 5.4 0 0 0-.2 3A5.8 5.8 0 0 0 2.2 7c0 5.8 3.5 7 6.8 7.4a4.8 4.8 0 0 0-1 3.5v4" /><path d="M8 19c-3 .9-3-1.5-4.2-2" /></svg>;
}

export function RefreshIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="M20 6v5h-5M4 18v-5h5" /><path d="M18.5 9A7 7 0 0 0 6.1 6.1L4 8m16 8-2.1 1.9A7 7 0 0 1 5.5 15" /></svg>;
}

export function CheckIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="m5 12 4 4L19 6" /></svg>;
}

export function SearchIcon(props: IconProps) {
  return <svg {...defaults} {...props}><circle cx="11" cy="11" r="7" /><path d="m20 20-4-4" /></svg>;
}

export function ThemeIcon(props: IconProps) {
  return <svg {...defaults} {...props}><path d="M20.5 15.5A8.5 8.5 0 0 1 8.5 3.5 8 8 0 1 0 20.5 15.5Z" /><path d="M17 4v3m1.5-1.5h-3" /></svg>;
}
