import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";
import { Providers } from "./providers";
import "./globals.css";

export const metadata = {
  title: "Lumen Console",
  description:
    "Phase E — TanStack Query, React Flow agent graphs, Monaco diff, live SSE",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <div className="shell">
            <Nav />
            <main className="main">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
