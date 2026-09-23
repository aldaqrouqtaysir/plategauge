import { useEffect } from "react";
import { isCurrentDocumentNavigation } from "./navigation";
import "./localPreview.css";

type Props = {
  current: "home" | "capture" | "evidence";
  onNavigate?: () => void;
};

/** Shared navigation for the explicitly enabled camera candidate. */
export default function LocalHeader({ current, onNavigate }: Props) {
  const base = import.meta.env.BASE_URL;
  useEffect(() => {
    const previousTitle = document.title;
    const titles = {
      home: "PlateGauge — Capture and compare",
      capture: "Capture — PlateGauge",
      evidence: "Evidence — PlateGauge",
    };
    document.title = titles[current];
    return () => { document.title = previousTitle; };
  }, [current]);
  return <header className="lp-header">
    <a className="lp-brand" href={base} onClick={(event) => { if (isCurrentDocumentNavigation(event)) onNavigate?.(); }} aria-label="PlateGauge">
      <span className="lp-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" focusable="false">
          <circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="5.5" />
          <path d="M12 1v3m11 8h-3M12 23v-3M1 12h3" />
        </svg>
      </span><span>PlateGauge</span>
    </a>
    <nav aria-label="Primary navigation">
      <a href={`${base}?capture=1`} onClick={(event) => { if (isCurrentDocumentNavigation(event)) onNavigate?.(); }} aria-current={current === "capture" ? "page" : undefined}>Capture</a>
      <a href={`${base}?view=evidence`} onClick={(event) => { if (isCurrentDocumentNavigation(event)) onNavigate?.(); }} aria-current={current === "evidence" ? "page" : undefined}>Evidence</a>
      <a href={`${base}#about`} onClick={(event) => { if (isCurrentDocumentNavigation(event)) onNavigate?.(); }}>About</a>
    </nav>
  </header>;
}
