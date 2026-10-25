export function cn(
  ...classes: Array<string | false | null | undefined>
): string {
  return classes.filter(Boolean).join(" ");
}

export function formatTimestamp(
  timestamp?: string
): string {
  if (!timestamp) {
    return "--:--:--";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }

  return date.toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

export function formatScore(
  score: number | undefined
): string {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return "0.00";
  }

  return score.toFixed(2);
}

export function truncate(
  value: string,
  length: number
): string {
  if (value.length <= length) {
    return value;
  }

  return `${value.slice(0, length)}…`;
}
