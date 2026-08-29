export function StreamingDot() {
  return (
    <span className="inline-flex gap-1">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-muted-foreground"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  );
}
