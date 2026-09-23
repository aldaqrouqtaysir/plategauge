import { Component, lazy, Suspense, type ReactNode } from "react";
import LocalHeader from "../localPreview/LocalHeader";
import { candidateContextAllowed, candidateView } from "./policy";
import "./candidate.css";

const Home = lazy(() => import("../localPreview/CaptureHome"));
const Camera = lazy(() => import("../captureCamera/CameraCapture"));
const Evidence = lazy(() => import("../App"));

class RecoveryBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  override render() {
    if (!this.state.failed) return this.props.children;
    return <main id="main" className="candidate-message" role="alert">
      <h1>This view could not be opened.</h1>
      <p>Your photos have not been uploaded. Reloading discards any unsaved photos in this page.</p>
      <button type="button" onClick={() => window.location.reload()}>Reload page</button>
    </main>;
  }
}

export default function CameraApplication() {
  const allowed = candidateContextAllowed(
    import.meta.env.VITE_PLATEGAUGE_CAMERA_CANDIDATE === "1",
    window.location.hostname,
    window.location.protocol,
    window.isSecureContext,
    window.top === window.self,
  );
  if (!allowed) {
    return <main id="main" className="candidate-message">
      <h1>Open PlateGauge directly in a supported browser.</h1>
      <p>This experimental camera build requires a secure, top-level page on the configured site or a loopback preview. No camera or model has started.</p>
    </main>;
  }
  const view = candidateView(window.location.search);
  return <RecoveryBoundary>
    <Suspense fallback={<main id="main" className="candidate-message" role="status">Preparing PlateGauge…</main>}>
      {view === "camera" ? <Camera /> : view === "evidence" ? <>
        <LocalHeader current="evidence" />
        <aside className="candidate-evidence-note" aria-label="About these results">
          These are frozen benchmark results, not validation of camera estimates.
          <a href={`${import.meta.env.BASE_URL}?capture=1`}>Return to capture</a>
        </aside>
        <div className="candidate-evidence"><Evidence /></div>
      </> : <Home />}
    </Suspense>
  </RecoveryBoundary>;
}
