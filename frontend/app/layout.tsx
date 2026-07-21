import type { Metadata } from "next";
import type { ReactNode } from "react";
import { CRYPTO_RANDOM_UUID_POLYFILL } from "@/lib/crypto-polyfill";
import "./globals.css";

export const metadata: Metadata = {
  title: "BackTestBench",
  description: "BackTestBench dashboard for backtesting",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: ReactNode;
}>) {
  return (
    <html lang="ru">
      <head>
        <script dangerouslySetInnerHTML={{ __html: CRYPTO_RANDOM_UUID_POLYFILL }} />
      </head>
      <body>{children}</body>
    </html>
  );
}