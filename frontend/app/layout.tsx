import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Chakra_Petch } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

// Wordmark-only font (see components/TopBar.tsx's "font-wordmark" usage) --
// a geometric, techy sans-serif for the SINDVA brand mark specifically.
// The rest of the UI stays on Inter/JetBrains Mono, unchanged.
const chakraPetch = Chakra_Petch({
  variable: "--font-wordmark-family",
  subsets: ["latin"],
  weight: ["600", "700"],
});

export const metadata: Metadata = {
  title: "SINDVA Marine Watch",
  description: "Satellite Oil-Spill Detection & AIS Vessel Attribution — SIH26143",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${chakraPetch.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-bg text-slate-200">{children}</body>
    </html>
  );
}
