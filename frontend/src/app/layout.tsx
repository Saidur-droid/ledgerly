import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ledgerly — Your business speaks.",
  description: "Understand your business performance in plain language with explainable AI.",
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL ?? "http://localhost:3000"),
  openGraph: {
    title: "Ledgerly — Your business speaks.",
    description: "Business intelligence that feels like a conversation.",
    type: "website",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "Ledgerly — Your business speaks." }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Ledgerly — Your business speaks.",
    description: "Business intelligence that feels like a conversation.",
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
