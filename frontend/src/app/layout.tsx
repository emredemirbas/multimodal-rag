import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Tutorial Workspace",
    template: "%s | Tutorial Workspace",
  },
  description: "A private workspace for learning from programming tutorials.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main-content">
          Skip to main content
        </a>
        <header className="site-header">
          <div className="site-header__inner">
            <Link className="brand" href="/projects">
              Tutorial Workspace
            </Link>
            <nav aria-label="Primary navigation">
              <Link href="/projects">Projects</Link>
              <Link href="/demo">Demo guide</Link>
            </nav>
          </div>
        </header>
        <main id="main-content" className="page-shell" tabIndex={-1}>
          {children}
        </main>
      </body>
    </html>
  );
}
