"use client";

import { Container } from "./Container";

const NAMES = [
  "Northwind",
  "Acme Health",
  "Lumen",
  "Riverside Legal",
  "Foundry",
  "BlueOrbit",
  "Kestrel",
  "Vantage",
];

export function LogoMarquee() {
  const track = [...NAMES, ...NAMES];
  return (
    <section className="border-y border-border bg-muted/30 py-10">
      <Container>
        <p className="text-center text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Powering everyday workflows for teams like
        </p>
        <div className="group relative mt-6 overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]">
          <div className="flex w-max animate-marquee items-center gap-12 group-hover:[animation-play-state:paused]">
            {track.map((name, i) => (
              <span
                key={`${name}-${i}`}
                className="whitespace-nowrap text-lg font-semibold tracking-tight text-muted-foreground/50"
              >
                {name}
              </span>
            ))}
          </div>
        </div>
      </Container>
    </section>
  );
}
