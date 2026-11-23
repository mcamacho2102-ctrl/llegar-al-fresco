import { Position } from "./model";
export const meters = (a: Position, b: Position) =>
  Math.hypot((a[0] - b[0]) * 84800, (a[1] - b[1]) * 111100);
export function progress(point: Position, points: Position[], previousM = 0) {
  let walked = 0,
    distance = Infinity,
    at = 0,
    rank = Infinity;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1],
      b = points[i],
      dx = (b[0] - a[0]) * 84800,
      dy = (b[1] - a[1]) * 111100;
    const length = Math.hypot(dx, dy);
    if (!length) continue;
    const t = Math.min(
      1,
      Math.max(
        0,
        ((point[0] - a[0]) * 84800 * dx + (point[1] - a[1]) * 111100 * dy) /
          (length * length),
      ),
    );
    const error = meters(point, [
      a[0] + t * (b[0] - a[0]),
      a[1] + t * (b[1] - a[1]),
    ]);
    const candidate = walked + t * length;
    const score = error + Math.min(9, Math.abs(candidate - previousM) / 10);
    if (score < rank) {
      rank = score;
      distance = error;
      at = candidate;
    }
    walked += length;
  }
  return { distance, at };
}
