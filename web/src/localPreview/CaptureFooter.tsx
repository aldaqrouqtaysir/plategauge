import "./localPreview.css";

/** Notices for the camera candidate; navigation clears any owned capture session. */
export default function CaptureFooter({ onNavigate }: { onNavigate?: () => void }) {
  const base = import.meta.env.BASE_URL;
  const source = import.meta.env.VITE_SOURCE_URL ?? "https://github.com/aldaqrouqtaysir/plategauge";
  return <footer className="lp-footer">
    <nav aria-label="Privacy and project information">
      <a href={`${base}legal/CAMERA_PRIVACY_NOTICE.md`} onClick={onNavigate}>Privacy</a>
      <a href={`${base}legal/NOTICE.txt`} onClick={onNavigate}>Attribution & notices</a>
      <a href={source} onClick={onNavigate} rel="noreferrer">Source</a>
    </nav>
    <p>Research model adapted from LeFood-Set v1 by Yuita Arum Sari, Yudi Arimba Wani, and Atsushi Nakazawa · CC BY 4.0. See notices for attribution and changes.</p>
    <p>Photos are processed on your device. Hosting and network providers may process ordinary request metadata.</p>
  </footer>;
}
