/** Fire a small celebration burst; no-op when the user prefers reduced motion. */
export async function celebrate() {
  if (typeof window === "undefined") return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const confetti = (await import("canvas-confetti")).default;
  confetti({
    particleCount: 90,
    spread: 70,
    origin: { y: 0.7 },
    colors: ["#6366F1", "#D946EF", "#F59E0B", "#FCD34D"],
  });
}
