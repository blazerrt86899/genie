import Link from "next/link";
import { Container } from "./Container";
import { GithubIcon, LinkedinIcon, XIcon } from "./social-icons";
import { Wordmark } from "./Wordmark";

const COLUMNS: { title: string; links: string[] }[] = [
  { title: "Product", links: ["Overview", "How it works", "Agents", "Pricing", "Changelog"] },
  { title: "Company", links: ["About", "Blog", "Careers", "Contact"] },
  { title: "Resources", links: ["Docs", "API reference", "Status", "Community"] },
  { title: "Legal", links: ["Privacy", "Terms", "Security", "DPA"] },
];

export function Footer() {
  return (
    <footer className="border-t border-border bg-muted/20">
      <Container className="py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_repeat(4,1fr)]">
          <div>
            <Wordmark />
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">
              Your wish, fulfilled. One conversation, a whole team of AI
              specialists.
            </p>
            <div className="mt-4 flex gap-3 text-muted-foreground">
              <a href="#" aria-label="X" className="hover:text-foreground">
                <XIcon className="h-4 w-4" />
              </a>
              <a href="#" aria-label="GitHub" className="hover:text-foreground">
                <GithubIcon className="h-4 w-4" />
              </a>
              <a href="#" aria-label="LinkedIn" className="hover:text-foreground">
                <LinkedinIcon className="h-4 w-4" />
              </a>
            </div>
          </div>

          {COLUMNS.map((col) => (
            <div key={col.title}>
              <h3 className="text-sm font-semibold">{col.title}</h3>
              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                {col.links.map((l) => (
                  <li key={l}>
                    <a href="#" className="hover:text-foreground">
                      {l}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-col items-center justify-between gap-3 border-t border-border pt-6 text-xs text-muted-foreground sm:flex-row">
          <p>© {new Date().getFullYear()} Genie. All rights reserved.</p>
          <p className="flex gap-4">
            <Link href="/sign-in" className="hover:text-foreground">
              Sign in
            </Link>
            <a href="#" className="hover:text-foreground">
              Privacy
            </a>
            <a href="#" className="hover:text-foreground">
              Terms
            </a>
          </p>
        </div>
      </Container>
    </footer>
  );
}
