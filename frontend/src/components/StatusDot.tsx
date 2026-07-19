type Props = {
  tone?: "success" | "warning" | "muted";
  label: string;
};

export function StatusDot({ tone = "muted", label }: Props) {
  return (
    <span className={`status-dot status-dot--${tone}`}>
      <span className="status-dot__mark" />
      {label}
    </span>
  );
}
