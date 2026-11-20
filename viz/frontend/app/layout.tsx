import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Nav } from "@/components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Carbon-aware MARL scheduling — progress",
  description:
    "Uncertainty-aware, decentralised carbon-aware scheduling across UK grid regions: data, calibrated bands, simulator baselines and the policy ladder.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <aside className="rail">
            <div className="brand">
              <span className="mark">
                <i className="dot" />
                B.Tech major project
              </span>
              <b>
                Carbon-aware
                <br />
                MARL scheduling
              </b>
            </div>
            <Nav />
            <div className="rail-foot">
              Every number here is read from a committed experiment artifact:
              config, run manifest, metrics. Nothing on these pages is typed in
              by hand or recomputed for display.
            </div>
          </aside>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
