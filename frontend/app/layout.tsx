import type { Metadata } from "next";
import fs from "fs";
import path from "path";
import "./globals.css";

export const metadata: Metadata = {
  title: "Amal — Teaching Assistant & Memory Dashboard",
  description:
    "Minimalist conversational assistant powered by Claude Haiku and LangGraph categorical memory.",
};

function getInlineCss(): string {
  try {
    const cssPath = path.join(process.cwd(), "app", "globals.css");
    return fs.readFileSync(cssPath, "utf-8");
  } catch {
    return "";
  }
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const inlineCss = getInlineCss();
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        {inlineCss && (
          <style dangerouslySetInnerHTML={{ __html: inlineCss }} />
        )}
      </head>
      <body>{children}</body>
    </html>
  );
}
