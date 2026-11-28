export const minute = 60_000;
export const hour = 60 * minute;
export const day = 24 * hour;
const jstOffset = 9 * hour;

export const jstStart = time => Math.floor((time + jstOffset) / day) * day - jstOffset;
export const jstDate = time => new Date(time + jstOffset).toISOString().slice(0, 10);
export const jstTime = time => new Date(time + jstOffset).toISOString().slice(5, 16).replace("T", " ");

export function parseCron(cron) {
  const match = /^(\d{1,2}) (\d{1,2}) (\*|\*\/([1-9]\d?)) \* \*$/.exec(cron);
  if (!match || Number(match[1]) > 59 || Number(match[2]) > 23 || Number(match[4] ?? 1) > 31)
    throw new Error("Unsupported schedule cron");
  return {offset:Number(match[1]) * minute + Number(match[2]) * hour, step:Number(match[4] ?? 1)};
}

// The range is inclusive. Cron's day-of-month step restarts at 1 in UTC.
export function slotsBetween(cron, from, through) {
  const {offset,step} = parseCron(cron);
  const dates = [];
  for (let midnight = Math.floor(from / day) * day; midnight <= through + 32 * day; midnight += day) {
    const plannedAt = midnight + offset;
    if (plannedAt < from || (new Date(midnight).getUTCDate() - 1) % step !== 0) continue;
    dates.push(plannedAt);
    if (plannedAt > through) break;
  }
  return dates.slice(0,-1).map((plannedAt,index) => ({plannedAt,nextAt:dates[index+1]}));
}
