import { useEffect, useRef, useState } from "react";
import { buildDeviceCheckReport, DEVICE_CHECKS, emptyCheckResults, safeDuration, type BrowserKind, type CheckOutcome, type DeviceKind, type DeviceObservations, type TestEnvironment } from "./deviceCheckReport";
import "./deviceCheck.css";

/** Receives only booleans/timings, never photos, masses, predictions or camera handles. */
export default function DeviceCheck({ observations }: { observations: DeviceObservations }) {
  const [device, setDevice] = useState<DeviceKind>("unspecified");
  const [browser, setBrowser] = useState<BrowserKind>("unspecified");
  const [browserVersion, setBrowserVersion] = useState("");
  const [environment, setEnvironment] = useState<TestEnvironment>("unspecified");
  const [checks, setChecks] = useState(emptyCheckResults);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const downloadUrls = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  useEffect(() => {
    const urls = downloadUrls.current;
    return () => { for (const [url, timer] of urls) { clearTimeout(timer); URL.revokeObjectURL(url); } urls.clear(); };
  }, []);

  const download = () => {
    setError(""); setMessage("");
    let url: string | undefined;
    let anchor: HTMLAnchorElement | undefined;
    try {
      const report = buildDeviceCheckReport({ device, browser, browserVersion, environment }, checks, observations);
      const blob = new Blob([JSON.stringify(report, null, 2) + "\n"], { type: "application/json" });
      url = URL.createObjectURL(blob);
      anchor = document.createElement("a"); anchor.href = url; anchor.download = "plategauge-device-check.json";
      document.body.appendChild(anchor); anchor.click();
      const ownedUrl = url;
      downloadUrls.current.set(ownedUrl, setTimeout(() => { URL.revokeObjectURL(ownedUrl); downloadUrls.current.delete(ownedUrl); }, 1_000));
      url = undefined;
      setMessage("Device-check download requested. It contains your selections and timings only, not photos or estimates. This is not accuracy validation or release approval.");
    } catch (cause) {
      if (url) URL.revokeObjectURL(url);
      setError(cause instanceof Error && cause.message.startsWith("Use a numeric browser version") ? cause.message : "The device-check file could not be prepared. Review your selections and try again.");
    } finally { anchor?.remove(); }
  };
  const duration = (value: number | null) => { const ms = safeDuration(value); return ms === null ? "Not observed" : `${ms.toLocaleString("en-US")} ms`; };

  return <details className="rc-device-check">
    <summary>Device check <span>(optional)</span></summary>
    <p>Record a short check on a named setup. Use non-food props if preferred; no photos are included in this report. Select outcomes only after trying them yourself. Simulated browser tests are not physical-device evidence.</p>
    <div className="dc-setup">
      <label>Device type<select value={device} onChange={(event) => setDevice(event.target.value as DeviceKind)}><option value="unspecified">Not specified</option><option value="laptop_desktop">Laptop / desktop</option><option value="android">Android</option><option value="iphone_ipad">iPhone / iPad</option><option value="other">Other</option></select></label>
      <label>Browser<select value={browser} onChange={(event) => setBrowser(event.target.value as BrowserKind)}><option value="unspecified">Not specified</option><option value="chrome">Chrome</option><option value="edge">Edge</option><option value="firefox">Firefox</option><option value="safari">Safari</option><option value="other">Other</option></select></label>
      <label>Browser version <span>(optional)</span><input type="text" inputMode="decimal" maxLength={35} autoComplete="off" spellCheck={false} value={browserVersion} placeholder="For example, 140.0" onChange={(event) => setBrowserVersion(event.target.value)} /></label>
      <label>Camera used for this check<select value={environment} onChange={(event) => setEnvironment(event.target.value as TestEnvironment)}><option value="unspecified">Not specified</option><option value="physical_device">Physical device camera</option><option value="simulated_camera">Simulated camera</option></select></label>
    </div>
    <p className="dc-note">Selecting a device here does not establish compatibility or accuracy. Record only the setup and behavior you actually tested.</p>
    <fieldset><legend>Your workflow observations</legend>{Object.entries(DEVICE_CHECKS).map(([key, label]) => <label className="dc-check" key={key}><span>{label}</span><select value={checks[key as keyof typeof checks]} onChange={(event) => setChecks((previous) => ({ ...previous, [key]: event.target.value as CheckOutcome }))}><option value="untested">Not tested</option><option value="pass">Worked as expected</option><option value="fail">Needs attention</option><option value="not_applicable">Not applicable</option></select></label>)}</fieldset>
    <dl className="dc-timings"><div><dt>Latest capture preparation</dt><dd>{duration(observations.latestCaptureMs)}</dd></div><div><dt>Latest estimate click → result</dt><dd>{duration(observations.latestEstimateWallMs)}</dd></div><div><dt>Latest model processing</dt><dd>{duration(observations.latestModelProcessingMs)}</dd></div></dl>
    <p className="dc-note">Single observations, not p95 performance. Capture preparation excludes framing and permission wait; model processing excludes capture. Peak memory is not measured. Other work running on this device can affect timings.</p>
    <div className="dc-actions"><button type="button" className="cp-secondary" onClick={download}>Download device check</button><button type="button" className="cp-text-button" onClick={() => { setDevice("unspecified"); setBrowser("unspecified"); setBrowserVersion(""); setEnvironment("unspecified"); setChecks(emptyCheckResults()); setError(""); setMessage("Device-check selections reset. Downloaded files are not deleted."); }}>Reset device check</button></div>
    {error && <p role="alert" className="dc-error">{error}</p>}
    {message && <p role="status">{message}</p>}
  </details>;
}
