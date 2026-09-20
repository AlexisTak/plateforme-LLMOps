import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Image from "next/image";
import Link from "next/link";
import { NavMenu } from "@/components/nav-menu";
import { HealthBadge } from "@/components/health-badge";
import { ProjectSwitcher } from "@/components/project-switcher";
import { ProjectProvider } from "@/lib/project-context";
import { ToastProvider } from "@/components/toast";
import { CommandPalette } from "@/components/command-palette";
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
  title: "OpenModels — Console",
  description: "Console de création, d’évaluation et d’exploitation d’agents IA.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="fr"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex bg-bg text-text-primary font-sans" suppressHydrationWarning>
        <ProjectProvider>
          <ToastProvider>
            <CommandPalette />
            <aside className="shrink-0 w-60 border-r border-border flex flex-col h-screen sticky top-0 overflow-y-auto">
              <Link href="/" aria-label="OpenModels — Accueil" className="block m-4 mb-2 shrink-0 rounded-lg bg-white px-2 py-1 shadow-[0_0_20px_rgba(79,140,255,0.16)] ring-1 ring-white/10 transition-transform hover:scale-[1.02] w-fit">
                <Image src="/logo.png" alt="OpenModels" width={2172} height={790} priority className="h-10 w-auto" />
              </Link>
              <div className="px-1 pb-2 flex-1">
                <NavMenu />
              </div>
              <div className="border-t border-border p-3 space-y-2">
                <ProjectSwitcher />
                <HealthBadge />
              </div>
            </aside>
            <main className="flex-1 min-w-0 px-6 py-8 max-w-6xl w-full mx-auto">{children}</main>
          </ToastProvider>
        </ProjectProvider>
      </body>
    </html>
  );
}
