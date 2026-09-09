import type { Metadata } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { NavLink } from "@/components/nav-link";
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

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  weight: ["500", "600"],
  style: ["normal"],
});

export const metadata: Metadata = {
  title: "Biscuits Focus — Console",
  description: "Dataset, training, evaluation and chat console for Biscuits Focus.",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/dataset", label: "Dataset" },
  { href: "/rag", label: "RAG" },
  { href: "/training", label: "Training" },
  { href: "/chat", label: "Chat" },
  { href: "/system", label: "System" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-text-primary font-sans" suppressHydrationWarning>
        <ProjectProvider>
          <header className="relative border-b border-border px-6 py-3.5 flex items-center gap-8 sticky top-0 bg-bg/90 backdrop-blur-sm z-10">
            <Link href="/" className="flex items-center gap-2 shrink-0">
              <span className="text-xl leading-none">🍪</span>
              <span className="font-display text-[17px] tracking-tight text-text-primary">Biscuits Focus</span>
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV.map((item) => (
                <NavLink key={item.href} href={item.href} label={item.label} />
              ))}
            </nav>
            <ProjectSwitcher />
            <HealthBadge />
          </header>
          <main className="flex-1 px-6 py-8 max-w-6xl w-full mx-auto">{children}</main>
        </ProjectProvider>
      </body>
    </html>
  );
}
