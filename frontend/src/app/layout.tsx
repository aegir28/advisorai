import type { Metadata, Viewport } from "next";
import { Fraunces, Geist, Geist_Mono } from "next/font/google";
import { BRAND } from "@/config/brand";
import { AuthProvider } from "@/features/auth/auth-context";
import { DisclaimerBar } from "@/components/layout/disclaimer-bar";
import { SafetyBanner } from "@/components/layout/safety-banner";
import { t } from "@/i18n";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const fraunces = Fraunces({ variable: "--font-fraunces", subsets: ["latin"], axes: ["opsz"] });

export const metadata: Metadata = {
  title: { default: `${BRAND.name} — second-opinion preparation`, template: `%s · ${BRAND.name}` },
  description: BRAND.description,
  applicationName: BRAND.name,
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f9f7f2",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} min-h-dvh`}>
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[60] focus:rounded-lg focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
        >
          {t("common.skipToContent")}
        </a>
        <AuthProvider>
          <SafetyBanner />
          {children}
          <DisclaimerBar />
        </AuthProvider>
      </body>
    </html>
  );
}
