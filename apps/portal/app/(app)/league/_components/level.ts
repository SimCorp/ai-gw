/**
 * Client-side level/XP derivation from lifetime League points.
 * Pure presentation — the backend only knows points.
 * Level N starts at 250·(N−1)² lifetime points.
 */
export interface LevelInfo {
  level: number;
  /** Points into the current level. */
  current: number;
  /** Points needed to reach the next level (from the start of this one). */
  span: number;
  /** 0..1 progress within the current level. */
  progress: number;
}

export function levelFor(lifetimePoints: number): LevelInfo {
  const xp = Math.max(0, lifetimePoints);
  const level = Math.floor(Math.sqrt(xp / 250)) + 1;
  const floor = 250 * (level - 1) ** 2;
  const ceil = 250 * level ** 2;
  const span = ceil - floor;
  const current = xp - floor;
  return { level, current, span, progress: Math.min(1, current / span) };
}
