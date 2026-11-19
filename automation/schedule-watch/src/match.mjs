import {hour, minute} from "./slots.mjs";

export const delayThreshold = 30 * minute;

export function scheduledRuns(runs, now) {
  return runs.filter(run => run.event === "schedule" && run.branch === "main" && run.createdAt <= now)
    .sort((a,b) => a.createdAt - b.createdAt || a.id - b.id);
}

// Slots are ascending and use half-open intervals to keep a boundary run in one slot.
export function matchRuns(slots, runs, now) {
  const candidates = scheduledRuns(runs, now);
  let index = 0;
  return slots.map(slot => {
    while (index < candidates.length && candidates[index].createdAt < slot.plannedAt) index++;
    if (candidates[index]?.createdAt < slot.nextAt) return candidates[index++];
    return null;
  });
}

export function slotState(slot, run, now) {
  if (run) return run.createdAt - slot.plannedAt <= delayThreshold ? "on_time" : "recovered";
  if (now >= slot.nextAt) return "missed";
  if (now >= slot.plannedAt + 12 * hour) return "still_missing";
  if (now >= slot.plannedAt + delayThreshold) return "late";
  return "waiting";
}
