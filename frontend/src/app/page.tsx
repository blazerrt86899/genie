import type { Metadata } from "next";
import { SiteHeader } from "@/components/landing/SiteHeader";
import { Hero } from "@/components/landing/Hero";
import { LogoMarquee } from "@/components/landing/LogoMarquee";
import { HowItWorks } from "@/components/landing/HowItWorks";
import { Features } from "@/components/landing/Features";
import { VoiceComingSoon } from "@/components/landing/VoiceComingSoon";
import { CtaBand } from "@/components/landing/CtaBand";
import { Footer } from "@/components/landing/Footer";

export const metadata: Metadata = {
  title: "Genie — your voice AI concierge",
  description:
    "Ask once. Genie routes your request to the right specialist agents and gets it done — web, calendar, tasks, documents. Voice coming soon.",
};

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main>
        <Hero />
        <LogoMarquee />
        <HowItWorks />
        <Features />
        <VoiceComingSoon />
        <CtaBand />
      </main>
      <Footer />
    </>
  );
}
