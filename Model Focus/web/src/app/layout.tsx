import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import { NavMenu } from "@/components/nav-menu";
import { HealthBadge } from "@/components/health-badge";
import { ProjectSwitcher } from "@/components/project-switcher";
import { ProjectProvider } from "@/lib/project-context";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "OpenAgent — Console",
  description: "Console de création, d’évaluation et d’exploitation d’agents IA.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text-primary font-sans" suppressHydrationWarning>
        <ProjectProvider>
          <header className="relative border-b border-border px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-x-4 lg:gap-x-8 gap-y-2 sticky top-0 bg-bg/90 backdrop-blur-md shadow-[0_8px_30px_rgba(0,0,0,0.18)] z-10">
            <Link href="/" aria-label="OpenAgent — Accueil" className="shrink-0 rounded-lg bg-white px-2 py-1 shadow-[0_0_20px_rgba(79,140,255,0.16)] ring-1 ring-white/10 transition-transform hover:scale-[1.02]">
              <Image src="/logo.png" alt="OpenAgent" width={2172} height={724} priority className="h-7 w-auto" />
            </Link>
            <NavMenu />
            <ProjectSwitcher />
            <HealthBadge />
          </header>
          <main className="flex-1 px-6 py-8 max-w-6xl w-full mx-auto">{children}</main>
        </ProjectProvider>
      </body>
    </html>
  );
}
