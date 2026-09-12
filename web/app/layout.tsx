import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

import { getViewer } from "@/lib/api";
import { BottomNav } from "@/components/bottom-nav";
import { EarlyAccessBanner } from "@/components/early-access-banner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/sidebar";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: {
    default: "Mokara",
    template: "%s · Mokara",
  },
  description:
    "Monte Carlo portfolio simulation — stress-test investment strategies across thousands of futures.",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  const viewer = await getViewer().catch(() => null);

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">
        <TooltipProvider delayDuration={200}>
          <div className="flex min-h-screen">
            <Sidebar viewer={viewer} />
            <div className="flex min-w-0 flex-1 flex-col pb-[calc(3.5rem+env(safe-area-inset-bottom))] md:pb-0">
              <SiteHeader viewer={viewer} />
              <EarlyAccessBanner />
              {children}
              <SiteFooter />
            </div>
          </div>
          <BottomNav />
        </TooltipProvider>
      </body>
    </html>
  );
}
