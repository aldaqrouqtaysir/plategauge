import { useEffect, type ReactNode } from "react";
import LocalHeader from "./LocalHeader";
import CaptureFooter from "./CaptureFooter";
import "./captureHome.css";

function HomeIcon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="ch-icon"
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

function Arrow() {
  return <HomeIcon><path d="M5 12h14m-5-5 5 5-5 5" /></HomeIcon>;
}

function Camera() {
  return (
    <HomeIcon>
      <path d="M8 6 9.5 4h5L16 6h3a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z" />
      <circle cx="12" cy="12.5" r="3.5" />
    </HomeIcon>
  );
}

function PlateIllustration({ after = false }: { after?: boolean }) {
  return (
    <svg className="ch-plate" viewBox="0 0 240 240" aria-hidden="true">
      <path d="M24 49V28h21M195 28h21v21M216 191v21h-21M45 212H24v-21" fill="none" stroke="#859b80" strokeWidth="1.6" strokeLinecap="round" />
      <ellipse cx="120" cy="126" rx="86" ry="83" fill="#d7e1d1" opacity=".55" />
      <circle cx="120" cy="120" r="85" fill="#fffefa" stroke="#d2ddc9" strokeWidth="1.4" />
      <circle cx="120" cy="120" r="68" fill="#f8f8ef" stroke="#e3e8d9" />
      <path d="M66 118c-1-29 18-51 45-54" fill="none" stroke="#fffefa" strokeWidth="5" strokeLinecap="round" />
      {after ? (
        <path d="M102 104c8-5 23-2 28 7 4 9-1 22-12 23-12 2-24-9-21-19 1-4 2-7 5-11Z" transform="translate(25 -3)" fill="#bf8355" />
      ) : (
        <>
          <path d="M102 104c8-5 23-2 28 7 4 9-1 22-12 23-12 2-24-9-21-19 1-4 2-7 5-11Z" transform="translate(-16 -14)" fill="#bf8355" />
          <path d="M102 104c8-5 23-2 28 7 4 9-1 22-12 23-12 2-24-9-21-19 1-4 2-7 5-11Z" transform="translate(25 -3)" fill="#bf8355" />
          <path d="M102 104c8-5 23-2 28 7 4 9-1 22-12 23-12 2-24-9-21-19 1-4 2-7 5-11Z" transform="translate(4 28)" fill="#bf8355" />
        </>
      )}
    </svg>
  );
}

function CaptureIllustration() {
  return (
    <figure className="ch-illustration" aria-labelledby="capture-illustration-caption">
      <div className="ch-illustration-heading">
        <span className="ch-illustration-mark"><Camera /></span>
        <span>Same plate. A second look.</span>
      </div>
      <div className="ch-illustrated-pair" aria-hidden="true">
        <div className="ch-illustrated-photo">
          <div className="ch-photo-label"><span>01</span><strong>Before</strong></div>
          <PlateIllustration />
        </div>
        <span className="ch-pair-arrow"><Arrow /></span>
        <div className="ch-illustrated-photo ch-illustrated-after">
          <div className="ch-photo-label"><span>02</span><strong>After</strong></div>
          <PlateIllustration after />
        </div>
      </div>
      <div className="ch-illustration-rule" aria-hidden="true">
        <span />
        <HomeIcon><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><circle cx="12" cy="12" r="4" /></HomeIcon>
        <span />
      </div>
      <figcaption id="capture-illustration-caption">
        Illustrative pair · not photographs or model output.
      </figcaption>
    </figure>
  );
}

export default function CaptureHome() {
  const captureUrl = `${import.meta.env.BASE_URL}?capture=1`;
  const evidenceUrl = `${import.meta.env.BASE_URL}?view=evidence`;

  useEffect(() => {
    if (window.location.hash === "#about") {
      document.getElementById("about")?.scrollIntoView({ behavior: "instant", block: "start" });
    }
  }, []);

  return (
    <div className="capture-home" data-testid="capture-home">
      <LocalHeader current="home" />
      <main id="main" tabIndex={-1} className="ch-main">
        <section className="ch-hero" aria-labelledby="capture-home-title">
          <div className="ch-hero-copy">
            <p className="ch-eyebrow">One plate. Two moments.</p>
            <h1 id="capture-home-title">Your plate.{" "}<span>Before and after.</span></h1>
            <p className="ch-lead">
              Capture one food item before and after, match the framing, and choose Estimate remaining.
              Your photos and the experimental estimate stay on your device.
            </p>
            <div className="ch-actions">
              <a className="ch-primary" href={captureUrl} aria-describedby="ch-capture-disclosure"><Camera />Start a capture<Arrow /></a>
              <a className="ch-secondary" href={evidenceUrl}>Explore the evidence<Arrow /></a>
            </div>
            <p className="ch-permission-note">Your camera stays off until you choose Open camera.</p>
            <p className="ch-scope-note" id="ch-capture-disclosure">
              <HomeIcon><circle cx="12" cy="12" r="9" /><path d="M12 11v5m0-9h.01" /></HomeIcon>
              <span>Experimental estimate using the v1 paired research baseline. Not validated for your photos and not a scale measurement.</span>
            </p>
          </div>
          <CaptureIllustration />
        </section>

        <section className="ch-workflow" aria-labelledby="capture-workflow-title">
          <div className="ch-section-heading">
            <p className="ch-eyebrow">A consistent pair</p>
            <h2 id="capture-workflow-title">Keep it simple. Keep the view consistent.</h2>
          </div>
          <ol className="ch-steps">
            <li>
              <div className="ch-step-top"><span className="ch-step-number">01</span><Camera /></div>
              <h3>Start with before.</h3>
              <p>Keep the food inside the model-view guide, use even lighting, and leave personal details out of frame.</p>
            </li>
            <li>
              <div className="ch-step-top">
                <span className="ch-step-number">02</span>
                <HomeIcon><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><circle cx="12" cy="12" r="4" /></HomeIcon>
              </div>
              <h3>Match the after photo.</h3>
              <p>Use the same plate, viewpoint, distance, and light. Keep the before photo as your reference.</p>
            </li>
            <li>
              <div className="ch-step-top">
                <span className="ch-step-number">03</span>
                <HomeIcon><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M12 4v16M7 9h1m8 6h1" /></HomeIcon>
              </div>
              <h3>Review and estimate.</h3>
              <p>Check the exact model input, then choose Estimate remaining. Retake if needed, and clear the pair when you finish.</p>
            </li>
          </ol>
        </section>

        <section id="about" className="ch-about" aria-labelledby="capture-about-title">
          <div className="ch-about-intro">
            <p className="ch-eyebrow">About PlateGauge</p>
            <h2 id="capture-about-title">A place to capture.<br /><span>Research to inspect.</span></h2>
            <p>
              PlateGauge combines camera capture, visual comparison, and an optional
              experimental estimate from the existing v1 paired baseline. It does not align
              photos or verify capture quality. The model has not been validated for user photos;
              no confidence interval or operational-use claim is made.
            </p>
            <a className="ch-evidence-link" href={evidenceUrl}>Inspect the benchmark and its limitations<Arrow /></a>
          </div>
          <div className="ch-privacy">
            <span className="ch-privacy-icon">
              <HomeIcon><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2" /></HomeIcon>
            </span>
            <div>
              <h3>On your device. Under your control.</h3>
              <p>
                Photos are not uploaded or automatically saved. There is no account or analytics.
                The model runs locally only when you choose Estimate remaining; it does not learn
                from your photos. Choose Save session to download an unencrypted file containing
                the photos and optional starting mass, then Resume session to continue later.
                Keep that file private and delete it when finished. Clearing, reloading, or leaving
                removes the pair from this page, but does not delete downloaded files.
              </p>
              <p>
                Camera access starts only when you choose Open camera. Audio is not requested,
                and hiding the tab stops the camera and clears estimates. Optional grams are
                calculated only from a starting mass you provide, not measured by the photos.
              </p>
            </div>
          </div>
        </section>
      </main>
      <CaptureFooter />
    </div>
  );
}
