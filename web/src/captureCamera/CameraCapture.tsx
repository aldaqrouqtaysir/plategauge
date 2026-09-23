import { useCallback, useEffect, useRef, useState } from "react";
import { boundedOperation } from "../capturePrototype/operations";
import { cameraErrorMessage, captureFrame, requestCamera, stopStream, type CameraPhoto } from "./camera";
import LocalHeader from "../localPreview/LocalHeader";
import CaptureFooter from "../localPreview/CaptureFooter";
import { estimatePair } from "../experimentalEstimator/estimate";
import { estimateErrorMessage } from "../experimentalEstimator/errors";
import { isCurrentDocumentNavigation } from "../localPreview/navigation";
import ModelCropPreview from "./ModelCropPreview";
import { getModelCropFrame } from "./framing";
import { createSessionFile, restoreSessionFile, SESSION_FILE_ACCEPT, sessionErrorMessage } from "./session";
import DeviceCheck from "./DeviceCheck";
import { parseStartingMass, STARTING_MASS_MAX_LENGTH } from "./startingMass";
import "../capturePrototype/capturePrototype.css";
import "./cameraCapture.css";

type Step = "before" | "after" | "review";
type CameraState = "idle" | "requesting" | "live" | "capturing";
const steps: Step[] = ["before", "after", "review"];
type EstimateValue = Awaited<ReturnType<typeof estimatePair>> & { initialMassG?: number };
type EstimateState = { status: "idle" | "running" } | { status: "error"; message: string } | { status: "complete"; value: EstimateValue };
type RestoredSession = Awaited<ReturnType<typeof restoreSessionFile>>;
type SessionState = { status: "idle" | "saving" | "restoring" | "confirm" | "saved" } | { status: "error"; message: string };

function releaseImportedPhotos(session: RestoredSession): void {
  for (const photo of new Set([session.before, session.after])) photo?.release();
}

const captureIcons = {
  plate: <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="5.5" /><path d="M12 1v3m11 8h-3M12 23v-3M1 12h3" /></>,
  camera: <><path d="M8 5 6.5 8H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-2.5L16 5Z" /><circle cx="12" cy="13.5" r="3.5" /></>,
  frame: <><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><circle cx="12" cy="12" r="4" /></>,
  info: <><circle cx="12" cy="12" r="9" /><path d="M12 11v6m0-10v.5" /></>,
  check: <path d="m5 12 4.5 4.5L19 7" />,
};

function CaptureIcon({ name }: { name: keyof typeof captureIcons }) {
  return <svg className="rc-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">{captureIcons[name]}</svg>;
}

/** Local, user-initiated capture with opt-in experimental baseline inference. No upload path. */
export default function CameraCapture() {
  const [step, setStep] = useState<Step>("before");
  const [cameraState, setCameraState] = useState<CameraState>("idle");
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [ready, setReady] = useState(false);
  const [previewAspect, setPreviewAspect] = useState(4 / 3);
  const [liveDimensions, setLiveDimensions] = useState<{ width: number; height: number } | null>(null);
  const [modelCropFrame, setModelCropFrame] = useState<ReturnType<typeof getModelCropFrame> | null>(null);
  const [showBeforeReference, setShowBeforeReference] = useState(false);
  const [before, setBefore] = useState<CameraPhoto | null>(null);
  const [after, setAfter] = useState<CameraPhoto | null>(null);
  const [comparison, setComparison] = useState<"pair" | "overlay">("pair");
  const [reviewImages, setReviewImages] = useState<"full" | "model">("full");
  const [opacity, setOpacity] = useState(50);
  const [startingMass, setStartingMass] = useState("");
  const [estimate, setEstimate] = useState<EstimateState>({ status: "idle" });
  const [latestCaptureMs, setLatestCaptureMs] = useState<number | null>(null);
  const [latestEstimateWallMs, setLatestEstimateWallMs] = useState<number | null>(null);
  const [sessionState, setSessionState] = useState<SessionState>({ status: "idle" });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("Your camera stays off until you choose Open camera.");
  const videoRef = useRef<HTMLVideoElement>(null);
  // React clears DOM refs before effect cleanup; retain the owned video until detached.
  const attachedVideo = useRef<HTMLVideoElement | null>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const estimateResultRef = useRef<HTMLDivElement>(null);
  const estimateErrorRef = useRef<HTMLDivElement>(null);
  const estimateCancelRef = useRef<HTMLButtonElement>(null);
  const estimateButtonRef = useRef<HTMLButtonElement>(null);
  const sessionFileRef = useRef<HTMLInputElement>(null);
  const sessionCancelRef = useRef<HTMLButtonElement>(null);
  const sessionKeepRef = useRef<HTMLButtonElement>(null);
  const sessionErrorRef = useRef<HTMLDivElement>(null);
  const sessionSaveRef = useRef<HTMLButtonElement>(null);
  const sessionResumeRef = useRef<HTMLButtonElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const captureRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const firstFrameTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const liveFrameSeen = useRef(false);
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const removeTrackListeners = useRef<(() => void) | null>(null);
  const owned = useRef(new Set<CameraPhoto>());
  const estimateActive = useRef<AbortController | null>(null);
  const estimateGeneration = useRef(0);
  const estimateStarted = useRef(false);
  const restoreEstimateFocus = useRef(false);
  const sessionActive = useRef<AbortController | null>(null);
  const sessionGeneration = useRef(0);
  const pendingRestore = useRef<RestoredSession | null>(null);
  const downloadUrls = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const restoreSessionFocus = useRef(false);
  const focusRestoredHeading = useRef(false);

  const releaseSessionOperation = useCallback(() => {
    sessionGeneration.current += 1;
    sessionActive.current?.abort();
    sessionActive.current = null;
    if (pendingRestore.current) releaseImportedPhotos(pendingRestore.current);
    pendingRestore.current = null;
  }, []);

  const invalidateSession = useCallback(() => {
    releaseSessionOperation(); setSessionState({ status: "idle" });
  }, [releaseSessionOperation]);

  const revokeDownloads = useCallback(() => {
    for (const [url, timer] of downloadUrls.current) { clearTimeout(timer); URL.revokeObjectURL(url); }
    downloadUrls.current.clear();
  }, []);

  const releaseEstimate = useCallback(() => {
    estimateGeneration.current += 1;
    estimateActive.current?.abort();
    estimateActive.current = null;
    estimateStarted.current = false;
  }, []);

  const invalidateEstimate = useCallback(() => {
    releaseEstimate();
    setLatestEstimateWallMs(null);
    setEstimate({ status: "idle" });
  }, [releaseEstimate]);

  const releaseCamera = useCallback(() => {
    generation.current += 1;
    if (firstFrameTimer.current !== null) clearTimeout(firstFrameTimer.current);
    firstFrameTimer.current = null;
    active.current?.abort();
    active.current = null;
    removeTrackListeners.current?.();
    removeTrackListeners.current = null;
    if (streamRef.current) stopStream(streamRef.current);
    streamRef.current = null;
    liveFrameSeen.current = false;
    const video = attachedVideo.current ?? videoRef.current;
    if (video) { video.pause(); video.srcObject = null; }
    attachedVideo.current = null;
  }, []);

  const closeCamera = useCallback(() => {
    releaseCamera(); setCameraState("idle"); setReady(false);
    setLiveDimensions(null); setModelCropFrame(null); setShowBeforeReference(false);
  }, [releaseCamera]);

  const failCamera = useCallback((message: string) => {
    closeCamera(); setError(message);
    setNotice("Camera stopped. Check the message above, then try again.");
  }, [closeCamera]);

  const updateReadiness = useCallback(() => {
    const video = videoRef.current; const stream = streamRef.current;
    if (!video || !stream || video.srcObject !== stream) return;
    if (video.videoWidth > 0 && video.videoHeight > 0 && (video.videoWidth < 224 || video.videoHeight < 224)) {
      failCamera("This camera's image is too small. Choose a camera that provides at least 224 pixels on each side.");
      return;
    }
    const live = stream.getVideoTracks().some((track) => track.readyState === "live" && track.enabled && !track.muted);
    const usable = live && video.readyState >= 2 && video.videoWidth >= 224 && video.videoHeight >= 224;
    if (video.videoWidth >= 224 && video.videoHeight >= 224) {
      try {
        const cropFrame = getModelCropFrame(video.videoWidth, video.videoHeight);
        setLiveDimensions({ width: video.videoWidth, height: video.videoHeight });
        setModelCropFrame(cropFrame);
        setPreviewAspect(video.videoWidth / video.videoHeight);
      } catch {
        failCamera("This camera's frame dimensions cannot be prepared safely. Choose another camera or a lower-resolution device setting.");
        return;
      }
    } else {
      setLiveDimensions(null); setModelCropFrame(null);
    }
    const liveAspect = video.videoWidth / video.videoHeight;
    const referenceAspect = before ? before.width / before.height : 0;
    const matchingReference = before && Math.abs(liveAspect - referenceAspect) / Math.max(liveAspect, referenceAspect) <= 0.05;
    if (!usable || !matchingReference) setShowBeforeReference(false);
    if (usable) {
      liveFrameSeen.current = true;
      if (firstFrameTimer.current !== null) clearTimeout(firstFrameTimer.current);
      firstFrameTimer.current = null;
    }
    setReady(usable);
  }, [failCamera, before]);

  const clearPhotos = useCallback(() => {
    closeCamera();
    setLatestCaptureMs(null);
    invalidateSession(); revokeDownloads();
    invalidateEstimate(); setStartingMass("");
    for (const photo of owned.current) photo.release();
    owned.current.clear();
    setBefore(null); setAfter(null); setError("");
    setComparison("pair"); setReviewImages("full"); setOpacity(50); setStep("before");
    setNotice("Photos cleared from this page. Downloaded session files are not deleted; remove those yourself when no longer needed.");
  }, [closeCamera, invalidateEstimate, invalidateSession, revokeDownloads]);

  useEffect(() => {
    const photos = owned.current;
    const onHidden = () => {
      if (document.visibilityState !== "hidden") return;
      const hadCamera = active.current !== null || streamRef.current !== null;
      const hadEstimate = estimateStarted.current;
      const hadSessionOperation = sessionActive.current !== null || pendingRestore.current !== null;
      closeCamera();
      invalidateEstimate();
      invalidateSession();
      if (hadSessionOperation) setNotice("Session operation cancelled because this tab was hidden. The current photos remain unchanged.");
      else if (hadCamera) setNotice("Camera stopped because this tab was hidden. Reopen it when you are ready.");
      else if (hadEstimate) setNotice("Estimate cleared because this tab was hidden. Your photos remain available; run a new estimate when ready.");
    };
    const onPageHide = () => clearPhotos();
    const onPageShow = (event: PageTransitionEvent) => { if (event.persisted) clearPhotos(); };
    document.addEventListener("visibilitychange", onHidden);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("pageshow", onPageShow);
    return () => {
      document.removeEventListener("visibilitychange", onHidden);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("pageshow", onPageShow);
      releaseCamera();
      releaseEstimate();
      releaseSessionOperation(); revokeDownloads();
      for (const photo of photos) photo.release();
      photos.clear();
    };
  }, [clearPhotos, closeCamera, releaseCamera, invalidateEstimate, releaseEstimate, invalidateSession, releaseSessionOperation, revokeDownloads]);

  const lastStep = useRef(step);
  useEffect(() => {
    if (lastStep.current !== step) titleRef.current?.focus();
    lastStep.current = step;
  }, [step]);
  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);
  useEffect(() => {
    if (sessionState.status === "saving" || sessionState.status === "restoring") sessionCancelRef.current?.focus();
    if (sessionState.status === "confirm") sessionKeepRef.current?.focus();
    if (sessionState.status === "error") sessionErrorRef.current?.focus();
    if (sessionState.status === "saved") sessionSaveRef.current?.focus();
    if (sessionState.status === "idle" && restoreSessionFocus.current) {
      restoreSessionFocus.current = false; sessionResumeRef.current?.focus();
    }
  }, [sessionState]);
  useEffect(() => {
    if (estimate.status === "running") estimateCancelRef.current?.focus();
    if (estimate.status === "complete") estimateResultRef.current?.focus();
    if (estimate.status === "error") estimateErrorRef.current?.focus();
    if (estimate.status === "idle" && restoreEstimateFocus.current) {
      restoreEstimateFocus.current = false;
      estimateButtonRef.current?.focus();
    }
  }, [estimate]);
  useEffect(() => {
    if (cameraState === "requesting") cancelRef.current?.focus();
    if (cameraState === "live" && ready) captureRef.current?.focus();
  }, [cameraState, ready]);
  useEffect(() => {
    if (cameraState === "idle" && ((step === "before" && before) || (step === "after" && after))) nextRef.current?.focus();
  }, [before, after, step, cameraState]);
  useEffect(() => {
    if (focusRestoredHeading.current && sessionState.status === "idle") {
      focusRestoredHeading.current = false;
      titleRef.current?.focus();
    }
  }, [sessionState, step]);

  const navigate = (next: Step) => {
    closeCamera(); invalidateEstimate(); invalidateSession(); setError(""); setStep(next);
    setNotice(next === "before" ? "Review your before photo, or retake it to start a new pair." : next === "after" ? "Use the same plate, camera, angle, and lighting for the after photo." : "Review your photos, then optionally run the experimental estimate. Nothing runs automatically.");
  };
  const discard = (photo: CameraPhoto | null) => {
    if (!photo) return;
    photo.release(); owned.current.delete(photo);
  };
  const retake = (role: "before" | "after") => {
    setLatestCaptureMs(null);
    closeCamera(); invalidateEstimate(); invalidateSession(); setStartingMass(""); setError(""); setComparison("pair"); setReviewImages("full");
    if (role === "before") { discard(before); setBefore(null); discard(after); setAfter(null); }
    else { discard(after); setAfter(null); }
    setStep(role);
    setNotice(role === "before" ? "Both photos cleared so the replacement pair starts together." : "After photo cleared. Open the camera to retake it.");
    titleRef.current?.focus();
  };

  const openCamera = async () => {
    closeCamera(); invalidateEstimate(); invalidateSession(); setError(""); setReady(false);
    setPreviewAspect(4 / 3);
    const controller = new AbortController(); active.current = controller;
    const current = generation.current;
    setCameraState("requesting");
    setNotice("Waiting for camera access. You can cancel without taking a photo.");
    try {
      const stream = await requestCamera(controller.signal, facing);
      if (current !== generation.current) { stopStream(stream); return; }
      streamRef.current = stream;
      const tracks = stream.getVideoTracks();
      if (tracks.length === 0 || tracks.every((track) => track.readyState === "ended")) throw new Error("The camera stream ended before it was ready.");
      const onEnded = () => {
        if (current !== generation.current) return;
        failCamera("Camera connection ended. Check your device and open the camera again.");
      };
      const onMuted = () => {
        if (current !== generation.current) return;
        if (!liveFrameSeen.current) { setReady(false); setNotice("Camera is warming up. Wait for a live frame, or close the camera to cancel."); return; }
        failCamera("The camera stopped supplying live frames. Open it again before taking a photo.");
      };
      const onUnmuted = () => { if (current === generation.current) updateReadiness(); };
      for (const track of tracks) { track.addEventListener("ended", onEnded); track.addEventListener("mute", onMuted); track.addEventListener("unmute", onUnmuted); }
      removeTrackListeners.current = () => { for (const track of tracks) { track.removeEventListener("ended", onEnded); track.removeEventListener("mute", onMuted); track.removeEventListener("unmute", onUnmuted); } };
      const video = videoRef.current;
      if (!video) throw new Error("The camera preview is unavailable.");
      attachedVideo.current = video;
      video.srcObject = stream;
      // A resolved play() is not proof that usable frames arrived. Bound that wait too.
      firstFrameTimer.current = setTimeout(() => {
        if (current !== generation.current || liveFrameSeen.current) return;
        failCamera("Camera did not provide a usable live image. Close other camera apps, check device permissions, and open the camera again.");
      }, 15_000);
      await boundedOperation(() => video.play(), controller.signal, () => undefined);
      if (current !== generation.current) return;
      setCameraState("live");
      updateReadiness();
      if (current !== generation.current) return;
      setNotice("Keep all of the food inside the model crop rectangle, then take the photo. The full camera frame is captured; no audio is requested.");
    } catch (cause) {
      if (current === generation.current) failCamera(cameraErrorMessage(cause));
    }
  };

  const takePhoto = async () => {
    const video = videoRef.current; const controller = active.current;
    if (!video || !controller || cameraState !== "live" || !ready || step === "review") return;
    const stream = streamRef.current;
    if (!stream || video.srcObject !== stream || !stream.getVideoTracks().some((track) => track.readyState === "live" && track.enabled && !track.muted)) {
      failCamera("A live camera frame is no longer available. Open the camera again."); return;
    }
    const current = generation.current; const role = step;
    const captureStartedAt = performance.now();
    setLatestCaptureMs(null);
    setCameraState("capturing"); setError("");
    try {
      const photo = await captureFrame(video, controller.signal);
      if (current !== generation.current) { photo.release(); return; }
      setLatestCaptureMs(performance.now() - captureStartedAt);
      owned.current.add(photo);
      if (role === "before") { discard(before); discard(after); setBefore(photo); setAfter(null); }
      else { discard(after); setAfter(photo); }
      closeCamera();
      setNotice(`${role === "before" ? "Before" : "After"} photo captured. Camera stopped; the photo stays only in this page's memory.`);
    } catch (cause) {
      if (current === generation.current) failCamera(cameraErrorMessage(cause));
    }
  };

  const selected = step === "before" ? before : after;
  const aspectBefore = before ? before.width / before.height : 1;
  const aspectAfter = after ? after.width / after.height : 1;
  const comparableShape = Math.abs(aspectBefore - aspectAfter) / Math.max(aspectBefore, aspectAfter) <= 0.05;
  const completePair = Boolean(before && after);
  const liveAspect = liveDimensions ? liveDimensions.width / liveDimensions.height : 0;
  const referenceMatches = Boolean(before && liveDimensions && Math.abs(aspectBefore - liveAspect) / Math.max(aspectBefore, liveAspect) <= 0.05);
  const referenceAvailable = step === "after" && cameraState === "live" && ready && referenceMatches;
  const parsedMass = parseStartingMass(startingMass);
  const sessionBusy = sessionState.status === "saving" || sessionState.status === "restoring";

  const applyRestoredSession = (restored: RestoredSession) => {
    // Ownership transfers only after the complete codec validation and any overwrite consent.
    pendingRestore.current = null;
    focusRestoredHeading.current = true;
    closeCamera(); invalidateEstimate();
    setLatestCaptureMs(null);
    for (const photo of owned.current) photo.release();
    owned.current.clear(); owned.current.add(restored.before);
    if (restored.after) owned.current.add(restored.after);
    setBefore(restored.before); setAfter(restored.after); setStartingMass(restored.startingMass);
    setError(""); setComparison("pair"); setReviewImages("full"); setOpacity(50);
    setStep(restored.after ? "review" : "after");
    setSessionState({ status: "idle" });
    setNotice(restored.after ? "Session restored locally. Review the pair; no camera or estimate started." : "Before photo restored locally. Open the camera when ready to take the after photo; no estimate started.");
  };

  const saveSession = async () => {
    if (!before || parsedMass.error || sessionActive.current || pendingRestore.current || document.visibilityState === "hidden") return;
    closeCamera(); invalidateEstimate(); invalidateSession(); setError("");
    const controller = new AbortController(); sessionActive.current = controller;
    const current = sessionGeneration.current;
    setSessionState({ status: "saving" }); setNotice("Preparing an unencrypted session file locally. Nothing is uploaded.");
    try {
      const blob = await createSessionFile({ before, after, startingMass }, controller.signal);
      if (controller.signal.aborted || current !== sessionGeneration.current) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      try {
        anchor.href = url; anchor.download = "plategauge-session.plategauge.json";
        anchor.hidden = true; document.body.append(anchor); anchor.click();
        // Give the browser time to consume the Blob for its download. Exit/reset also revokes it.
        const timer = setTimeout(() => { URL.revokeObjectURL(url); downloadUrls.current.delete(url); }, 60_000);
        downloadUrls.current.set(url, timer);
      } catch (cause) {
        URL.revokeObjectURL(url); throw cause;
      } finally { anchor.remove(); }
      setSessionState({ status: "saved" });
      setNotice("Download requested. Check your browser's downloads before leaving. The file is unencrypted; keep it private and delete it when finished.");
    } catch (cause) {
      if (controller.signal.aborted || current !== sessionGeneration.current) return;
      setSessionState({ status: "error", message: sessionErrorMessage(cause) });
      setNotice("Session file could not be prepared. The current photos and starting mass are unchanged.");
    } finally {
      if (current === sessionGeneration.current) sessionActive.current = null;
    }
  };

  const resumeSession = async (file: File) => {
    if (document.visibilityState === "hidden") return;
    closeCamera(); invalidateEstimate(); invalidateSession(); setError("");
    const controller = new AbortController(); sessionActive.current = controller;
    const current = sessionGeneration.current;
    setSessionState({ status: "restoring" }); setNotice("Checking the session file locally. Current photos are kept until validation and any replacement confirmation succeed.");
    try {
      const restored = await restoreSessionFile(file, controller.signal);
      if (controller.signal.aborted || current !== sessionGeneration.current) { releaseImportedPhotos(restored); return; }
      if (owned.current.size > 0) {
        pendingRestore.current = restored;
        setSessionState({ status: "confirm" });
        setNotice("Session file checked. Confirm whether to replace the current photos and starting mass.");
      } else applyRestoredSession(restored);
    } catch (cause) {
      if (controller.signal.aborted || current !== sessionGeneration.current) return;
      setSessionState({ status: "error", message: sessionErrorMessage(cause) });
      setNotice("Session could not be restored. The current photos and starting mass are unchanged.");
    } finally {
      if (current === sessionGeneration.current) sessionActive.current = null;
    }
  };
  const runEstimate = async () => {
    if (!before || !after || !comparableShape || parsedMass.error || estimateActive.current || document.visibilityState === "hidden") return;
    closeCamera(); invalidateEstimate(); invalidateSession();
    const controller = new AbortController();
    estimateActive.current = controller; estimateStarted.current = true;
    const current = estimateGeneration.current;
    const initialMassG = parsedMass.value;
    const estimateStartedAt = performance.now();
    setEstimate({ status: "running" });
    setNotice("Preparing and running the existing v1 paired baseline locally. You can cancel the estimate.");
    try {
      const value = await estimatePair(before, after, controller.signal);
      if (controller.signal.aborted || current !== estimateGeneration.current) return;
      if (!Number.isFinite(value.leftoverFraction) || value.leftoverFraction < 0 || value.leftoverFraction > 1 || !Number.isFinite(value.processingMs) || value.processingMs < 0 || !value.modelVersion.trim()) {
        throw new Error("Invalid estimate result");
      }
      setEstimate({ status: "complete", value: { ...value, ...(initialMassG === undefined ? {} : { initialMassG }) } });
      setLatestEstimateWallMs(performance.now() - estimateStartedAt);
      setNotice("Experimental estimate ready. This baseline is unvalidated for your photos; the result is not a measurement.");
    } catch (cause) {
      if (controller.signal.aborted || current !== estimateGeneration.current) return;
      setEstimate({ status: "error", message: estimateErrorMessage(cause) });
      setNotice("Estimate failed. No numeric result is available.");
    } finally {
      if (current === estimateGeneration.current) estimateActive.current = null;
    }
  };
  const cameraLabel = cameraState === "requesting" ? "Opening camera"
    : cameraState === "capturing" ? "Capturing photo"
    : cameraState === "live" ? ready ? "Camera on · ready" : "Preparing live image"
    : "Camera off";
  const retakeWarning = completePair ? "Retaking the before photo also clears the after photo. You will need to capture both again." : undefined;

  return <div className="cp-app rc-app" data-testid="camera-capture">
    <a className="cp-skip-link" href="#main">Skip to capture workflow</a>
    <LocalHeader current="capture" onNavigate={clearPhotos} />
    <main className="cp-main" id="main" tabIndex={-1}>
      <a className="lp-back-home" href={import.meta.env.BASE_URL} onClick={(event) => { if (isCurrentDocumentNavigation(event)) clearPhotos(); }}><span aria-hidden="true">←</span> Back to home</a>
      <div className="cp-intro"><div><p className="cp-eyebrow">Your plate. Your camera. Your device.</p><h1>A clearer picture<br /><span className="rc-hero-accent">of what remains.</span></h1></div><p>Take two photos. Match the framing. Review the difference — with your photos kept on your device.</p></div>
      <div className="cp-boundary" id="rc-capture-disclosure"><CaptureIcon name="info" /><p><strong>Experimental estimate.</strong> Uses the v1 paired research baseline. Not validated for user photos or field use; not a scale measurement.</p></div>
      <ol className="cp-steps" aria-label="Capture steps">{steps.map((item, index) => <li key={item}><button type="button" aria-current={step === item ? "step" : undefined} data-complete={item === "before" ? Boolean(before) : item === "after" ? Boolean(after) : estimate.status === "complete"} disabled={(item === "after" && !before) || (item === "review" && !completePair)} onClick={() => navigate(item)}><span>{String(index + 1).padStart(2, "0")}</span><strong>{item === "review" ? "Review & estimate" : `${item === "before" ? "Before" : "After"} photo`}</strong><small>{item === "before" ? before ? "Photo captured ✓" : "Set the starting point" : item === "after" ? after ? "Photo captured ✓" : "Match your framing" : estimate.status === "complete" ? "Estimate ready" : "Inspect the model input"}</small></button></li>)}</ol>
      <div className="cp-workspace"><section className="cp-card" aria-labelledby="rc-step-title">
        <div className="cp-card-heading"><div><p className="cp-eyebrow">Step {steps.indexOf(step) + 1} of 3</p><h2 id="rc-step-title" ref={titleRef} tabIndex={-1}>{step === "before" ? "Start with a full view." : step === "after" ? "Same plate. Same perspective." : "Review the pair. Then estimate."}</h2></div><span className="cp-step-glyph"><CaptureIcon name="frame" /></span></div>
        {step !== "review" ? <>
          <p className="cp-instruction">{step === "before" ? "Keep all of one food item inside the model crop rectangle. Keep the plate visible, use even lighting, and leave personal details out of frame." : "Keep the food inside the model crop and match your before photo: same plate, camera, orientation, distance, and light."}</p>
          {step === "after" && before && <figure className="rc-reference">
            <img src={before.url} alt="Before photo reference" />
            <figcaption><strong>Your before photo</strong><span>Use the plate edges and background to match your framing. This is a visual reference, not an alignment check.</span></figcaption>
          </figure>}
          <div className="rc-camera-state" data-active={cameraState === "live" && ready}>
            <span className="rc-state-dot" aria-hidden="true" />
            <strong>{cameraLabel}</strong><span>No audio</span>
          </div>
          <div className="cp-viewfinder rc-viewfinder" data-testid="live-viewfinder" hidden={cameraState === "idle"} style={{ aspectRatio: previewAspect, maxWidth: `${previewAspect * 420}px` }}>
            <video ref={videoRef} muted playsInline aria-label={`Live ${step} camera preview`} onCanPlay={updateReadiness} onResize={updateReadiness} />
            {showBeforeReference && referenceAvailable && before && <img className="rc-live-reference" data-testid="live-before-reference" src={before.url} alt="Before photo framing reference" style={{ opacity: 0.35 }} />}
            {modelCropFrame && liveDimensions && <div className="rc-model-crop-frame" data-testid="model-crop-frame" data-source-width={liveDimensions.width} data-source-height={liveDimensions.height} style={{ left: `${modelCropFrame.left}%`, top: `${modelCropFrame.top}%`, width: `${modelCropFrame.width}%`, height: `${modelCropFrame.height}%` }} aria-hidden="true"><span>Model input area</span></div>}
            <span className="cp-frame-tag">{cameraLabel}</span>
          </div>
          {cameraState !== "idle" && modelCropFrame && <p className="rc-crop-help">Keep all the food inside this rectangle. The model uses a central crop, not the full photo. Check Model input after capture.</p>}
          {step === "after" && before && <div className="rc-live-reference-control"><label><input type="checkbox" checked={showBeforeReference && referenceAvailable} disabled={!referenceAvailable} aria-describedby="rc-live-reference-help" onChange={(event) => setShowBeforeReference(event.target.checked && referenceAvailable)} />Show before reference</label><p id="rc-live-reference-help">A faint visual guide, not automatic registration or an alignment check. {cameraState === "live" && ready && !referenceMatches ? "Unavailable: the live image and before photo shapes differ by more than 5%." : !referenceAvailable ? "Available once a matching live after image is ready." : "Match the plate and background yourself; the photo is captured without the overlay."}</p></div>}
          {cameraState === "idle" && (selected ? <div className="cp-selected-preview"><img src={selected.url} alt={`Your ${step} photo`} /><span className="cp-frame-tag">{step === "before" ? "Before" : "After"} photo · camera stopped</span></div> : <div className="cp-empty-preview"><span className="rc-empty-mark"><CaptureIcon name="plate" /></span><strong>{step === "before" ? "Begin with the before photo" : "Bring the after photo into frame"}</strong><p>Your camera starts only when you choose Open camera.</p></div>)}
          {cameraState === "idle" ? <div className="cp-input-controls">
            {selected ? <button className="cp-secondary" type="button" aria-describedby={step === "before" && retakeWarning ? "rc-retake-warning" : undefined} onClick={() => retake(step)}>Retake {step}</button> : <>
              <label htmlFor="rc-facing">Preferred camera<select id="rc-facing" value={facing} onChange={(event) => setFacing(event.target.value === "user" ? "user" : "environment")}><option value="environment">Rear / outward-facing</option><option value="user">Front / user-facing</option></select></label>
              <button className="cp-primary" type="button" aria-describedby="rc-capture-disclosure" onClick={() => void openCamera()}><CaptureIcon name="camera" />Open camera</button>
            </>}
          </div> : <div className="cp-action-row rc-camera-actions">
            {cameraState !== "requesting" && <button ref={captureRef} className="cp-primary" type="button" disabled={!ready || cameraState === "capturing"} onClick={() => void takePhoto()}><CaptureIcon name="camera" />{cameraState === "capturing" ? "Capturing photo…" : `Take ${step} photo`}</button>}
            <button ref={cancelRef} className="cp-secondary" type="button" onClick={() => { closeCamera(); setNotice("Camera request cancelled and this page's camera tracks stopped. No new photo was kept."); titleRef.current?.focus(); }}>{cameraState === "requesting" ? "Cancel camera request" : "Close camera"}</button>
          </div>}
          {step === "before" && retakeWarning && <p id="rc-retake-warning" className="rc-retake-warning">{retakeWarning}</p>}
          <div className="cp-card-bottom"><small>No uploads · estimate only when requested</small><button ref={nextRef} type="button" className="cp-primary" disabled={!selected || cameraState !== "idle"} onClick={() => navigate(step === "before" ? "after" : "review")}>{step === "before" ? "Continue to after" : "Review & estimate"}<span aria-hidden="true">→</span></button></div>
        </> : <>
          <div className="cp-comparison-controls rc-review-source" role="group" aria-label="Review image source"><button type="button" className="cp-secondary" aria-pressed={reviewImages === "full"} onClick={() => setReviewImages("full")}>Full photos</button><button type="button" className="cp-secondary" aria-pressed={reviewImages === "model"} onClick={() => setReviewImages("model")}>Model input</button></div>
          <p className="rc-crop-help">{reviewImages === "full" ? "Inspect the full photos, then check Model input to see the exact 224 × 224 crops used for inference." : "These are the exact 224 × 224 model crops before normalization. Check that all of the food is visible; this preview does not run a prediction or verify the pair."}</p>
          {reviewImages === "full" && <div className="cp-comparison-controls" role="group" aria-label="Photo comparison view"><button className="cp-secondary" type="button" aria-pressed={comparison === "pair"} onClick={() => setComparison("pair")}>Side by side</button><button className="cp-secondary" type="button" disabled={!comparableShape} aria-pressed={comparison === "overlay"} onClick={() => setComparison("overlay")}>Compare framing</button></div>}
          {!comparableShape && <p className="rc-device-help" id="rc-shape-error">The photo shapes differ by more than 5%. Keep the same orientation and camera when retaking them. Overlay comparison and estimation are unavailable for this pair.</p>}
          {reviewImages === "full" && comparison === "overlay" && comparableShape && before && after && <div className="cp-comparison" data-testid="framing-comparison"><div className="cp-overlay-images"><img src={before.url} alt="Before photo beneath the overlay" /><img src={after.url} style={{ opacity: opacity / 100 }} alt="After photo in the overlay" /></div><label htmlFor="rc-opacity">Blend the photos <output htmlFor="rc-opacity">{opacity}% after</output></label><input id="rc-opacity" type="range" min="0" max="100" value={opacity} onChange={(event) => setOpacity(Number(event.target.value))} aria-valuetext={opacity === 0 ? "Before photo only" : opacity === 100 ? "After photo only" : `${opacity}% after photo over before photo`} aria-describedby="rc-overlay-help" /><div className="rc-overlay-endpoints" aria-hidden="true"><span>Before only</span><span>After only</span></div><p id="rc-overlay-help">Visual comparison only; it does not align or validate the photos.</p></div>}
          <div className={`cp-review-pair ${reviewImages === "model" ? "rc-model-review" : ""}`}>{([["before", before], ["after", after]] as const).map(([role, photo]) => <figure key={role}>{photo && (reviewImages === "model" ? <ModelCropPreview photo={photo} label={`${role === "before" ? "Before" : "After"} model input`} /> : <img src={photo.url} alt={`Your ${role} photo for review`} />)}<figcaption><strong>{role === "before" ? "Before" : "After"}</strong><button className="cp-text-button" type="button" aria-describedby={role === "before" && retakeWarning ? "rc-retake-warning" : undefined} onClick={() => retake(role)}>Retake {role}</button></figcaption></figure>)}</div>
          {retakeWarning && <p id="rc-retake-warning" className="rc-retake-warning">{retakeWarning}</p>}
          <section className="rc-estimator" aria-labelledby="rc-estimator-title">
            <div className="rc-estimator-heading"><p className="cp-eyebrow">Local inference · only when requested</p><h3 id="rc-estimator-title">Estimate the fraction remaining.</h3></div>
            <p id="rc-estimator-scope">Uses the v1 paired research baseline, which has not been validated for your photos. No confidence interval is available. This result is not a scale measurement and must not guide nutrition, health, procurement, or other operational decisions.</p>
            <label className="rc-mass-label" htmlFor="rc-starting-mass">Starting food mass (g, optional)
              <input id="rc-starting-mass" type="text" inputMode="decimal" maxLength={STARTING_MASS_MAX_LENGTH} autoComplete="off" spellCheck={false} value={startingMass} aria-invalid={Boolean(parsedMass.error)} aria-describedby={parsedMass.error ? "rc-mass-help rc-mass-error" : "rc-mass-help"} onChange={(event) => { invalidateEstimate(); invalidateSession(); setStartingMass(event.target.value); setNotice("Starting mass updated. Run an estimate to apply it to this pair."); }} />
            </label>
            <p id="rc-mass-help" className="rc-estimate-help">Use the initial net food mass, excluding the plate. Leave blank for a fraction-only result. Grams are calculated only from the starting mass you supply.</p>
            {parsedMass.error && <p id="rc-mass-error" className="rc-estimate-field-error" role="alert">{parsedMass.error}</p>}
            <div className="rc-estimate-actions">
              <button ref={estimateButtonRef} type="button" className="cp-primary" disabled={!completePair || !comparableShape || Boolean(parsedMass.error) || estimate.status === "running"} aria-describedby={`rc-estimator-scope${!comparableShape ? " rc-shape-error" : ""}`} onClick={() => void runEstimate()}>Estimate remaining</button>
              {estimate.status === "running" && <button ref={estimateCancelRef} type="button" className="cp-secondary" onClick={() => { restoreEstimateFocus.current = true; invalidateEstimate(); setNotice("Estimate cancelled. No result was kept. Your photos remain available for another attempt."); }}>Cancel estimate</button>}
            </div>
            {estimate.status === "running" && <p className="rc-estimate-progress" role="status" aria-live="polite">Preparing images and running the baseline on your device…</p>}
            {estimate.status === "error" && <div ref={estimateErrorRef} tabIndex={-1} className="cp-error" role="alert"><strong>Estimate unavailable</strong><p>{estimate.message}</p><button type="button" className="cp-secondary" onClick={() => void runEstimate()}>Retry estimate</button></div>}
            {estimate.status === "complete" && <div ref={estimateResultRef} tabIndex={-1} className="rc-estimate-result" data-testid="experimental-estimate-result" data-leftover-fraction={estimate.value.leftoverFraction} data-model-version={estimate.value.modelVersion} data-processing-ms={estimate.value.processingMs} data-remaining-mass-g={estimate.value.initialMassG === undefined ? undefined : estimate.value.initialMassG * estimate.value.leftoverFraction} aria-labelledby="rc-estimate-result-title">
              <p className="cp-eyebrow">Existing v1 paired baseline</p><h3 id="rc-estimate-result-title">Experimental estimate</h3>
              <p className="rc-estimate-number">{(estimate.value.leftoverFraction * 100).toFixed(1)}%<span>estimated remaining</span></p>
              {estimate.value.initialMassG !== undefined && <p className="rc-estimate-mass" data-testid="experimental-estimate-mass">{(estimate.value.leftoverFraction * estimate.value.initialMassG).toLocaleString("en-US", { maximumFractionDigits: 1 })} g estimated remaining <span>Calculated from your {estimate.value.initialMassG.toLocaleString("en-US", { maximumFractionDigits: 6 })} g starting mass, not measured from the photos.</span></p>}
              <p>Unvalidated for your photos. Not a measurement or an operational recommendation.</p>
              <p className="rc-estimate-metadata">Model {estimate.value.modelVersion} · {estimate.value.processingMs.toLocaleString("en-US", { maximumFractionDigits: 0 })} ms processing</p>
            </div>}
          </section>
        </>}
        {error && <div ref={errorRef} tabIndex={-1} className="cp-error" role="alert"><strong>Camera needs attention</strong><p>{error}</p></div>}
        <p className="rc-session-status" role="status" aria-live="polite" aria-atomic="true">{notice}</p>
        {step !== "review" && <details className="rc-help" open={Boolean(error)}><summary>Camera permissions and troubleshooting</summary><p>Your browser chooses the closest available camera. Allow camera access when prompted; audio is never requested.</p><p>If an embedded view blocks access, open this page directly in your browser. Check browser and device permissions, and close other apps using the camera.</p><p>You can cancel a request here, but only your browser can dismiss its permission prompt.</p></details>}
        <section className="rc-session-files" data-testid="session-controls" aria-labelledby="rc-session-files-title">
          <div><p className="cp-eyebrow">Pause now. Pick up later.</p><h3 id="rc-session-files-title">Keep your place.</h3></div>
          <p>Save after the before photo, or keep the complete pair. Resume only your own PlateGauge session files; ordinary image uploads are not supported.</p>
          <p className="rc-session-disclosure" id="rc-session-disclosure"><strong>The downloaded file is unencrypted.</strong> It contains your photos and any starting mass, but no estimates. Keep it private and delete it when finished. Clearing this page does not delete downloaded files.</p>
          <div className="rc-session-file-actions">
            <button ref={sessionSaveRef} type="button" className="cp-secondary" disabled={!before || Boolean(parsedMass.error) || sessionBusy || sessionState.status === "confirm"} aria-describedby="rc-session-disclosure" onClick={() => void saveSession()}>Save session</button>
            <button ref={sessionResumeRef} type="button" className="cp-secondary" disabled={sessionBusy || sessionState.status === "confirm"} aria-describedby="rc-session-disclosure" onClick={() => { closeCamera(); invalidateEstimate(); invalidateSession(); sessionFileRef.current?.click(); }}>Resume session</button>
            <input ref={sessionFileRef} hidden type="file" accept={SESSION_FILE_ACCEPT} aria-label="PlateGauge session file" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void resumeSession(file); }} />
            {sessionBusy && <button ref={sessionCancelRef} type="button" className="cp-secondary" onClick={() => { restoreSessionFocus.current = true; invalidateSession(); setNotice("Session operation cancelled. The current photos and starting mass remain unchanged."); }}>Cancel session operation</button>}
          </div>
          {sessionBusy && <p className="rc-session-file-progress">{sessionState.status === "saving" ? "Preparing your download…" : "Checking your session file…"}</p>}
          {sessionState.status === "confirm" && <div className="rc-session-confirmation" data-testid="session-replace-confirmation" role="region" aria-labelledby="rc-session-replace-title">
            <h4 id="rc-session-replace-title">Replace current session?</h4><p>The file is valid. Replacing will clear this page’s current photos and starting mass, and load the saved ones. No camera or estimate will start.</p>
            <div className="rc-session-file-actions"><button ref={sessionKeepRef} type="button" className="cp-secondary" onClick={() => { restoreSessionFocus.current = true; invalidateSession(); setNotice("Current session kept. The imported photos were discarded from this page."); }}>Keep current session</button><button type="button" className="cp-primary" onClick={() => { const restored = pendingRestore.current; if (restored) applyRestoredSession(restored); }}>Replace current session</button></div>
          </div>}
          {sessionState.status === "error" && <div ref={sessionErrorRef} tabIndex={-1} className="cp-error" data-testid="session-error" role="alert"><strong>Session needs attention</strong><p>{sessionState.message}</p></div>}
        </section>
        <DeviceCheck observations={{ cameraReadyNow: ready, beforePresent: Boolean(before), afterPresent: Boolean(after), latestCaptureMs, latestEstimateWallMs, latestModelProcessingMs: estimate.status === "complete" ? estimate.value.processingMs : null }} />
        <div className="cp-session"><p>Leaving or reloading clears this page. Only a session file you choose to download can be resumed later.</p><button className="cp-text-button" type="button" onClick={() => { clearPhotos(); titleRef.current?.focus(); }}>Clear photos</button></div>
      </section><aside className="cp-guide" aria-label="Capture guidance"><p className="cp-eyebrow">A consistent pair</p><h2>{step === "review" ? "Check what is included." : <>Small details. <br />Better captures.</>}</h2>{step === "review" ? <p className="rc-review-help">Switch to Model input and check both crops before estimating. If food is cut off, retake the photo. Matching shapes and visible food do not establish capture quality or model accuracy.</p> : <ol><li><span>01</span><div><h3>Food inside the crop</h3><p>Keep all of one food item inside the crop rectangle. Avoid personal details anywhere in the full camera frame.</p></div></li><li><span>02</span><div><h3>Match the second photo</h3><p>Use the same viewpoint, orientation, distance, and light. The optional before reference is a visual guide, not registration.</p></div></li><li><span>03</span><div><h3>Review & estimate</h3><p>Inspect the model crops, then choose Estimate remaining. Nothing runs automatically.</p></div></li></ol>}<div className="cp-privacy-note"><strong>On your device. Under your control.</strong><p>No accounts, photo uploads, analytics, automatic saving, or browser history of captures. Session files are downloaded only when you choose Save session. Model assets load locally when requested; photos are not used to train a model. Hiding the tab stops the camera and clears estimates; clearing, reloading, or leaving removes photos from this page, not from your downloads.</p></div></aside></div>
    </main>
    <CaptureFooter onNavigate={clearPhotos} />
  </div>;
}
