import type { LevelInfo } from "./level";

export default function XPBar({ info }: { info: LevelInfo }) {
  return (
    <div className="lg-xp">
      <div className="lg-xp__meta">
        <span>LVL {info.level}</span>
        <span>
          {info.current.toLocaleString()} / {info.span.toLocaleString()} XP
        </span>
      </div>
      <div className="lg-xp__track">
        <div className="lg-xp__fill" style={{ width: `${Math.round(info.progress * 100)}%` }} />
      </div>
    </div>
  );
}
