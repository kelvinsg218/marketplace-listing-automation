import type { Metadata, Viewport } from "next";
import { JetBrains_Mono, Manrope } from "next/font/google";
import { SessionProvider } from "@/lib/session";
import "./globals.css";

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope", display: "swap" });
const jetbrains = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains", display: "swap" });

export const metadata: Metadata = {
  title: { default: "MLA", template: "%s · MLA" },
  description: "Catálogo inteligente e preparação de anúncios em massa.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { themeColor: "#090909", colorScheme: "dark" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR" className={`${manrope.variable} ${jetbrains.variable}`}>
      <body><SessionProvider>{children}</SessionProvider></body>
    </html>
  );
}
