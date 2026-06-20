export default function LevelBadge({ level, size = "md" }: { level: number; size?: "md" | "sm" }) {
  return (
    <div className={`lg-level${size === "sm" ? " lg-level--sm" : ""}`} title={`Level ${level}`}>
      <div className="lg-level__shape" />
      <span className="lg-level__num">{level}</span>
    </div>
  );
}
