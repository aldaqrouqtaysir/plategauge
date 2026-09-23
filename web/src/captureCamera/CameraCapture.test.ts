import { createElement } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import CameraCapture from "./CameraCapture";
import { captureFrame, requestCamera, stopStream, type CameraPhoto } from "./camera";
import type * as CameraModule from "./camera";
import { estimatePair } from "../experimentalEstimator/estimate";
import { EstimateError, estimateErrorMessage } from "../experimentalEstimator/errors";
import { createSessionFile, restoreSessionFile } from "./session";
import type { DeviceObservations } from "./deviceCheckReport";

vi.mock("../experimentalEstimator/estimate", () => ({ estimatePair: vi.fn() }));
vi.mock("./ModelCropPreview", () => ({ default: ({ label }: { photo: CameraPhoto; label: string }) => createElement("canvas", { width: 224, height: 224, role: "img", "aria-label": label, "data-testid": "model-crop-preview" }) }));
vi.mock("./DeviceCheck", () => ({ default: ({ observations }: { observations: DeviceObservations }) => createElement("div", { "data-testid": "device-check-observations", "data-observations": JSON.stringify(observations) }) }));
vi.mock("./session", () => ({ createSessionFile: vi.fn(), restoreSessionFile: vi.fn(), SESSION_FILE_ACCEPT: ".plategauge.json", sessionErrorMessage: () => "The session file could not be processed safely." }));

vi.mock("./camera", async (original) => {
  const actual = await original<typeof CameraModule>();
  return { ...actual, requestCamera: vi.fn(), captureFrame: vi.fn(), stopStream: vi.fn() };
});

function syntheticStream() {
  const track = Object.assign(new EventTarget(), {
    kind: "video", readyState: "live", enabled: true, muted: false,
    stop: vi.fn(() => { track.readyState = "ended"; }),
  });
  const stream = {
    getTracks: () => [track], getVideoTracks: () => [track], getAudioTracks: () => [],
  } as unknown as MediaStream;
  return { stream, track };
}

function syntheticPhoto(label: string) {
  return { width: 640, height: 480, url: `blob:generated-${label}`, release: vi.fn(), copyPixels: vi.fn(() => ({ width: 224, height: 224, data: new Uint8ClampedArray(224 * 224 * 4).fill(255) })) };
}

function deferredEstimate() {
  let resolve!: (value: Awaited<ReturnType<typeof estimatePair>>) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Awaited<ReturnType<typeof estimatePair>>>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function deferredSession() {
  let resolve!: (value: Awaited<ReturnType<typeof restoreSessionFile>>) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<Awaited<ReturnType<typeof restoreSessionFile>>>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}

function restoredPair() { return { before: syntheticPhoto("import-before"), after: syntheticPhoto("import-after"), startingMass: "240" }; }
function chooseSession() {
  const file = new File(["synthetic session"], "fixture.plategauge.json", { type: "application/json" });
  fireEvent.change(screen.getByLabelText("PlateGauge session file"), { target: { files: [file] } });
  return file;
}

const mockEstimate = { leftoverFraction: 0.375, modelVersion: "v1-paired-test", processingMs: 12.5 };
const originalCreateUrl = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const originalRevokeUrl = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
const createUrl = vi.fn(() => "blob:session-download");
const revokeUrl = vi.fn();
const anchorClick = vi.fn();

async function take(role: "before" | "after"): Promise<void> {
  fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
  const button = await screen.findByRole("button", { name: `Take ${role} photo` });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await waitFor(() => expect(screen.getByRole("button", { name: role === "before" ? "Continue to after" : "Review & estimate" })).toBeEnabled());
}

async function pair(): Promise<void> {
  await take("before");
  fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
  await take("after");
  fireEvent.click(screen.getByRole("button", { name: "Review & estimate" }));
}

describe("user-initiated camera component with fully mocked hardware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(4);
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(640);
    vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(480);
    vi.mocked(requestCamera).mockImplementation(() => Promise.resolve(syntheticStream().stream));
    vi.mocked(stopStream).mockImplementation((stream) => stream.getTracks().forEach((track) => track.stop()));
    let photoNumber = 0;
    vi.mocked(captureFrame).mockImplementation(() => Promise.resolve(syntheticPhoto(String(++photoNumber))));
    vi.mocked(estimatePair).mockReset().mockResolvedValue(mockEstimate);
    vi.mocked(createSessionFile).mockReset().mockResolvedValue(new Blob(["synthetic session"], { type: "application/json" }));
    vi.mocked(restoreSessionFile).mockReset();
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createUrl });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revokeUrl });
    anchorClick.mockReset(); vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(anchorClick);
  });
  afterEach(() => {
    cleanup(); vi.restoreAllMocks(); vi.useRealTimers();
    if (originalCreateUrl) Object.defineProperty(URL, "createObjectURL", originalCreateUrl); else Reflect.deleteProperty(URL, "createObjectURL");
    if (originalRevokeUrl) Object.defineProperty(URL, "revokeObjectURL", originalRevokeUrl); else Reflect.deleteProperty(URL, "revokeObjectURL");
  });

  it("keeps the capture introduction concise without hiding action-boundary warnings", () => {
    const view = render(createElement(CameraCapture));
    expect(screen.queryByText(/Take two photos\. Match the framing/)).not.toBeInTheDocument();
    expect(view.container.querySelector(".cp-intro")?.children).toHaveLength(1);
    expect(screen.getByRole("heading", { name: "Capture checklist" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open camera" })).toHaveAccessibleDescription(/Not validated for your photos or field use; not a scale measurement/);
    expect(screen.getByRole("button", { name: "Save session" })).toHaveAccessibleDescription(/unencrypted.*photos and starting mass.*does not delete the file/);
    const privacy = screen.getByText("Privacy & storage").closest("details");
    expect(privacy).not.toHaveAttribute("open");
    expect(privacy).toHaveTextContent("photos are not used to train a model");
    expect(privacy).toHaveTextContent("Hiding the tab stops the camera and clears estimates");
    expect(view.container.querySelector(".rc-session-status")).toBeEmptyDOMElement();
    expect(requestCamera).not.toHaveBeenCalled(); expect(estimatePair).not.toHaveBeenCalled();
  });

  it("never requests a camera on mount and exposes only a session-file picker, not image uploads", () => {
    const view = render(createElement(CameraCapture));
    expect(requestCamera).not.toHaveBeenCalled();
    expect(captureFrame).not.toHaveBeenCalled();
    expect(estimatePair).not.toHaveBeenCalled();
    expect(view.container.querySelectorAll('input[type="file"]')).toHaveLength(1);
    expect(screen.getByLabelText("PlateGauge session file")).toHaveAttribute("accept", ".plategauge.json");
    expect(screen.getByLabelText("PlateGauge session file")).not.toHaveAttribute("capture");
    expect(view.container.querySelector('input[type="number"]')).toBeNull();
    expect(createSessionFile).not.toHaveBeenCalled(); expect(restoreSessionFile).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save session" })).toBeDisabled();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /02 After photo/ })).toBeDisabled();
    expect(screen.queryByText("Private camera preview")).not.toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toHaveTextContent("CC BY 4.0");
    expect(screen.getByRole("button", { name: "Open camera" })).toHaveAccessibleDescription(/Not validated for user photos or field use; not a scale measurement/);
    expect(screen.queryByText("PlateGauge / camera preview")).not.toBeInTheDocument();
    expect(screen.queryByText("Local development · on-device capture · no inference")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PlateGauge" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to home" })).toBeInTheDocument();
  });

  it.each([
    ["Back to home", "/"], ["PlateGauge", "/"], ["Capture", "/?capture=1"],
    ["Evidence", "/?view=evidence"], ["About", "/#about"],
    ["Privacy", "/legal/CAMERA_PRIVACY_NOTICE.md"], ["Attribution & notices", "/legal/NOTICE.txt"],
    ["Source", "https://github.com/aldaqrouqtaysir/plategauge"],
  ])("clears photos and stops the owned stream before returning through %s", async (name, href) => {
    const before = syntheticPhoto("before-home");
    vi.mocked(captureFrame).mockResolvedValueOnce(before);
    const view = render(createElement(CameraCapture));
    await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    const video = view.container.querySelector("video")!;
    expect(video.srcObject).toBe(stream);
    const link = screen.getByRole("link", { name });
    expect(link).toHaveAttribute("href", href);
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(track.stop).toHaveBeenCalledOnce();
    expect(video.srcObject).toBeNull();
    expect(before.release).toHaveBeenCalledOnce();
    expect(vi.mocked(requestCamera).mock.calls.at(-1)![0].aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Continue to after" })).toBeDisabled();
    expect(screen.queryByRole("img", { name: "Before photo reference" })).not.toBeInTheDocument();
    view.unmount();
    expect(before.release).toHaveBeenCalledOnce();
  });

  it.each(["Back to home", "PlateGauge", "Capture", "Evidence", "About", "Privacy", "Attribution & notices", "Source"])("preserves unsaved photos when %s is opened in another tab", async (name) => {
    const before = syntheticPhoto("before-new-tab"); vi.mocked(captureFrame).mockResolvedValueOnce(before);
    render(createElement(CameraCapture)); await take("before");
    const link = screen.getByRole("link", { name });
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link, { ctrlKey: true });
    expect(before.release).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Your before photo" })).toHaveAttribute("src", before.url);
    expect(screen.getByRole("button", { name: "Continue to after" })).toBeEnabled();
    // An actual document exit still owns final cleanup.
    fireEvent(window, new Event("pagehide"));
    expect(before.release).toHaveBeenCalledOnce();
  });

  it("preserves a capture if another handler prevents navigation", async () => {
    const before = syntheticPhoto("prevented-navigation"); vi.mocked(captureFrame).mockResolvedValueOnce(before);
    render(createElement(CameraCapture)); await take("before");
    const link = screen.getByRole("link", { name: "Evidence" });
    link.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(before.release).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Your before photo" })).toBeInTheDocument();
  });

  it("stops a late permission result after the home action cancels its request", async () => {
    let resolve!: (stream: MediaStream) => void;
    vi.mocked(requestCamera).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    const link = screen.getByRole("link", { name: "Back to home" });
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(vi.mocked(requestCamera).mock.calls[0]![0].aborted).toBe(true);
    const { stream, track } = syntheticStream();
    await act(async () => { resolve(stream); await Promise.resolve(); });
    expect(track.stop).toHaveBeenCalledOnce();
    expect(captureFrame).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Take before photo" })).not.toBeInTheDocument();
  });

  it("releases a late capture result after the home action clears the session", async () => {
    let resolve!: (photo: CameraPhoto) => void;
    vi.mocked(captureFrame).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    const capture = await screen.findByRole("button", { name: "Take before photo" });
    await waitFor(() => expect(capture).toBeEnabled());
    fireEvent.click(capture);
    const link = screen.getByRole("link", { name: "Back to home" });
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    const photo = syntheticPhoto("late-home");
    await act(async () => { resolve(photo); await Promise.resolve(); });
    expect(photo.release).toHaveBeenCalledOnce();
    expect(screen.queryByRole("img", { name: "Your before photo" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to after" })).toBeDisabled();
  });

  it("stops and detaches the live stream on unmount", async () => {
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    const view = render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take before photo" });
    const video = view.container.querySelector("video")!;
    expect(video.srcObject).toBe(stream);
    view.unmount();
    expect(track.stop).toHaveBeenCalled();
    expect(video.srcObject).toBeNull();
    expect(vi.mocked(requestCamera).mock.calls[0]![0].aborted).toBe(true);
  });

  it("stops a permission result that arrives after unmount", async () => {
    let resolve!: (stream: MediaStream) => void;
    vi.mocked(requestCamera).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const view = render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    view.unmount();
    const { stream, track } = syntheticStream();
    await act(async () => { resolve(stream); await Promise.resolve(); });
    expect(track.stop).toHaveBeenCalled();
    expect(captureFrame).not.toHaveBeenCalled();
  });

  it("discards a capture result that arrives after clearing", async () => {
    let resolve!: (photo: CameraPhoto) => void;
    vi.mocked(captureFrame).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    fireEvent.click(await screen.findByRole("button", { name: "Take before photo" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    const photo = syntheticPhoto("late");
    await act(async () => { resolve(photo); await Promise.resolve(); });
    expect(photo.release).toHaveBeenCalledOnce();
    expect(screen.queryByRole("img", { name: "Your before photo" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue to after" })).toBeDisabled();
  });

  it("releases an owned pair on unmount", async () => {
    const before = syntheticPhoto("before"), after = syntheticPhoto("after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    const view = render(createElement(CameraCapture)); await pair(); view.unmount();
    expect(before.release).toHaveBeenCalledOnce(); expect(after.release).toHaveBeenCalledOnce();
  });

  it("clears both pictures when retaking before", async () => {
    const before = syntheticPhoto("before"), after = syntheticPhoto("after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Retake before" }));
    expect(before.release).toHaveBeenCalledOnce(); expect(after.release).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /03 Review/ })).toBeDisabled();
  });

  it("opens review and estimate without predicting or an obsolete finish action", async () => {
    render(createElement(CameraCapture)); await pair();
    expect(screen.getByRole("heading", { name: "Review the pair. Then estimate." })).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Finish review" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("camera-review-result")).not.toBeInTheDocument();
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeEnabled();
    expect(captureFrame).toHaveBeenCalledTimes(2);
    expect(estimatePair).not.toHaveBeenCalled();
  });

  it("ignores a stale request rejection after a later session succeeds", async () => {
    let reject!: (error: Error) => void;
    vi.mocked(requestCamera).mockReturnValueOnce(new Promise((_done, fail) => { reject = fail; }));
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel camera request" }));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take before photo" });
    await act(async () => { reject(new Error("stale camera error")); await Promise.resolve(); });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Take before photo" })).toBeEnabled();
  });

  it("stops when a live track is muted even though video readiness is stale", async () => {
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take before photo" });
    act(() => { track.muted = true; track.dispatchEvent(new Event("mute")); });
    await waitFor(() => expect(track.stop).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveFocus());
    expect(captureFrame).not.toHaveBeenCalled();
  });

  it("rejects a nonzero but undersized ready frame and releases the stream", async () => {
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(160);
    vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(120);
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("alert");
    expect(track.stop).toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Camera stopped. Check the message above, then try again.");
    expect(captureFrame).not.toHaveBeenCalled();
  });

  it("allows a muted startup stream to unmute before enabling capture", async () => {
    const { stream, track } = syntheticStream(); track.muted = true;
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    const capture = await screen.findByRole("button", { name: "Take before photo" });
    expect(capture).toBeDisabled();
    expect(track.stop).not.toHaveBeenCalled();
    act(() => { track.muted = false; track.dispatchEvent(new Event("unmute")); });
    await waitFor(() => expect(capture).toBeEnabled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("clears owned photos on persisted pageshow", async () => {
    const before = syntheticPhoto("before"), after = syntheticPhoto("after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    render(createElement(CameraCapture)); await pair();
    act(() => {
      const event = new Event("pageshow"); Object.defineProperty(event, "persisted", { value: true });
      window.dispatchEvent(event);
    });
    expect(before.release).toHaveBeenCalledOnce(); expect(after.release).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Continue to after" })).toBeDisabled();
  });

  it("focuses the cancellation control while permission is pending", () => {
    vi.mocked(requestCamera).mockReturnValueOnce(new Promise(() => {}));
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    expect(screen.getByRole("button", { name: "Cancel camera request" })).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent(/waiting for camera access/i);
    fireEvent.click(screen.getByRole("button", { name: "Cancel camera request" }));
    expect(screen.getByRole("heading", { name: "Start with a full view." })).toHaveFocus();
    expect(vi.mocked(requestCamera).mock.calls[0]![0].aborted).toBe(true);
  });

  it("bounds first-frame preparation and does not revive after its deadline", async () => {
    vi.useFakeTimers();
    vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(0);
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(0);
    vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(0);
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    const view = render(createElement(CameraCapture));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open camera" })); await Promise.resolve(); });
    expect(screen.getByRole("button", { name: "Take before photo" })).toBeDisabled();
    expect(screen.getByText("Preparing live image", { selector: ".cp-frame-tag" })).toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(14_999); });
    expect(track.stop).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(track.stop).toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Camera did not provide a usable live image");
    expect(screen.getByRole("alert")).toHaveFocus();
    const video = view.container.querySelector("video")!;
    expect(video.srcObject).toBeNull();
    vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(4);
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(640);
    vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(480);
    fireEvent.canPlay(video);
    expect(screen.queryByRole("button", { name: "Take before photo" })).not.toBeInTheDocument();
    expect(captureFrame).not.toHaveBeenCalled();
  });

  it("cancels the first-frame deadline after a usable frame arrives", async () => {
    vi.useFakeTimers();
    const readiness = vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(0);
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    const view = render(createElement(CameraCapture));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Open camera" })); await Promise.resolve(); });
    expect(screen.getByRole("button", { name: "Take before photo" })).toBeDisabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    readiness.mockReturnValue(4);
    fireEvent.canPlay(view.container.querySelector("video")!);
    expect(screen.getByRole("button", { name: "Take before photo" })).toBeEnabled();
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(track.stop).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the before reference only for the after step and hides irrelevant camera choices", async () => {
    render(createElement(CameraCapture));
    expect(screen.getByRole("combobox", { name: "Preferred camera" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Before photo reference" })).not.toBeInTheDocument();
    await take("before");
    expect(screen.queryByRole("combobox", { name: "Preferred camera" })).not.toBeInTheDocument();
    const beforeUrl = screen.getByRole("img", { name: "Your before photo" }).getAttribute("src");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    expect(screen.getByRole("img", { name: "Before photo reference" })).toHaveAttribute("src", beforeUrl);
    expect(screen.getByRole("combobox", { name: "Preferred camera" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /01 Before photo/ }));
    expect(screen.getByRole("status")).toHaveTextContent("Review your before photo, or retake it to start a new pair.");
  });

  it("describes the before-retake consequence and releases only after when retaking after", async () => {
    const before = syntheticPhoto("before"), after = syntheticPhoto("after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    const view = render(createElement(CameraCapture)); await pair();
    expect(screen.getByRole("button", { name: "Retake before" })).toHaveAccessibleDescription(/after/i);
    fireEvent.click(screen.getByRole("button", { name: "Retake after" }));
    expect(after.release).toHaveBeenCalledOnce();
    expect(before.release).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Before photo reference" })).toHaveAttribute("src", before.url);
    view.unmount();
    expect(before.release).toHaveBeenCalledOnce();
    expect(after.release).toHaveBeenCalledOnce();
  });

  it("preserves photos while hidden without preserving a live camera", async () => {
    const before = syntheticPhoto("before");
    vi.mocked(captureFrame).mockResolvedValueOnce(before);
    const { stream, track } = syntheticStream();
    render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    expect(track.stop).toHaveBeenCalled();
    expect(before.release).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Before photo reference" })).toHaveAttribute("src", before.url);
  });

  it("releases a capture result arriving after unmount exactly once", async () => {
    let resolve!: (photo: CameraPhoto) => void;
    vi.mocked(captureFrame).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    const view = render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    fireEvent.click(await screen.findByRole("button", { name: "Take before photo" }));
    view.unmount();
    const photo = syntheticPhoto("unmounted");
    await act(async () => { resolve(photo); await Promise.resolve(); });
    expect(photo.release).toHaveBeenCalledOnce();
  });

  it("disables overlay and estimation for different photo shapes, retaining visual review", async () => {
    const before = syntheticPhoto("before"), after = { ...syntheticPhoto("after"), width: 480, height: 640 };
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    render(createElement(CameraCapture)); await pair();
    expect(screen.getByRole("button", { name: "Compare framing" })).toBeDisabled();
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toHaveAttribute("src", before.url);
    expect(screen.getByRole("img", { name: "Your after photo for review" })).toHaveAttribute("src", after.url);
    expect(screen.queryByTestId("framing-comparison")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Finish review" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeDisabled();
    expect(estimatePair).not.toHaveBeenCalled();
  });

  it("runs the baseline only after an explicit click and shows a fraction-only experimental result", async () => {
    render(createElement(CameraCapture)); await pair();
    expect(estimatePair).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toHaveAccessibleDescription(/v1 paired research baseline, which has not been validated for your photos/);
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toHaveAccessibleDescription(/No confidence interval is available/);
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toHaveAccessibleDescription(/not a scale measurement/);
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const result = await screen.findByTestId("experimental-estimate-result");
    await waitFor(() => expect(result).toHaveFocus());
    expect(result).toHaveTextContent("Experimental estimate");
    expect(result).toHaveTextContent("37.5%");
    expect(result).toHaveTextContent("Unvalidated for your photos");
    expect(result).toHaveAttribute("data-leftover-fraction", "0.375");
    expect(result).toHaveAttribute("data-model-version", "v1-paired-test");
    expect(result).toHaveAttribute("data-processing-ms", "12.5");
    expect(result).not.toHaveAttribute("data-remaining-mass-g");
    expect(screen.queryByTestId("experimental-estimate-mass")).not.toBeInTheDocument();
    expect(estimatePair).toHaveBeenCalledOnce();
    expect(vi.mocked(estimatePair).mock.calls[0]).toHaveLength(3);
  });

  it.each([100, 0.5, 100_000])("converts only the supplied positive starting mass %s", async (mass) => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: String(mass) } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const result = await screen.findByTestId("experimental-estimate-result");
    expect(result).toHaveAttribute("data-remaining-mass-g", String(mass * mockEstimate.leftoverFraction));
    expect(screen.getByTestId("experimental-estimate-mass")).toHaveTextContent(/not measured from the photos/);
    expect(vi.mocked(estimatePair).mock.calls[0]).toHaveLength(3);
  });

  it.each(["0", "-1", "100001", "Infinity", "NaN", "1e309", "not a mass", "0x20"])("rejects invalid supplied mass %s without inference", async (value) => {
    render(createElement(CameraCapture)); await pair();
    const input = screen.getByLabelText("Starting food mass (g, optional)");
    fireEvent.change(input, { target: { value } });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("or leave it blank");
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeDisabled();
    expect(estimatePair).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeEnabled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("aligns UI and export mass lengths without silently changing a supplied value", async () => {
    render(createElement(CameraCapture)); await pair();
    const input = screen.getByLabelText("Starting food mass (g, optional)");
    expect(input).toHaveAttribute("maxlength", "64");
    // Programmatic input can bypass the native limit; validation must remain fail-closed.
    fireEvent.change(input, { target: { value: "0".repeat(64) + "1" } });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("64 characters");
    expect(screen.getByRole("button", { name: "Save session" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeDisabled();
    expect(createSessionFile).not.toHaveBeenCalled(); expect(estimatePair).not.toHaveBeenCalled();
    const boundary = "0".repeat(63) + "1";
    fireEvent.change(input, { target: { value: boundary } });
    expect(input).toHaveAttribute("aria-invalid", "false");
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await waitFor(() => expect(createSessionFile).toHaveBeenCalledOnce());
    expect(vi.mocked(createSessionFile).mock.calls[0]![0].startingMass).toBe(boundary);
  });

  it("accepts exact zero output without inventing nonzero remaining mass", async () => {
    vi.mocked(estimatePair).mockResolvedValueOnce({ ...mockEstimate, leftoverFraction: 0 });
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    expect(await screen.findByTestId("experimental-estimate-result")).toHaveAttribute("data-remaining-mass-g", "0");
  });

  it("clears a finished estimate when its starting mass changes", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "250" } });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(estimatePair).toHaveBeenCalledOnce();
  });

  it("cancels a pending estimate and ignores its late result", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    expect(screen.getByRole("button", { name: "Cancel estimate" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeDisabled();
    const signal = vi.mocked(estimatePair).mock.calls[0]![2];
    fireEvent.click(screen.getByRole("button", { name: "Cancel estimate" }));
    expect(signal.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toHaveFocus();
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeEnabled();
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toBeInTheDocument();
  });

  it("does not let an older generation overwrite a newer successful estimate", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel estimate" }));
    vi.mocked(estimatePair).mockResolvedValueOnce({ ...mockEstimate, leftoverFraction: 0.8 });
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    await act(async () => { pending.resolve({ ...mockEstimate, leftoverFraction: 0.1 }); await Promise.resolve(); });
    expect(screen.getByTestId("experimental-estimate-result")).toHaveAttribute("data-leftover-fraction", "0.8");
  });

  it("shows allowlisted actionable estimator errors without losing the pair", async () => {
    const error = new EstimateError("identical_pair");
    vi.mocked(estimatePair).mockRejectedValueOnce(error);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(alert).toHaveTextContent(estimateErrorMessage(error));
    expect(alert).toHaveTextContent(/identical|same/i);
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Your after photo for review" })).toBeInTheDocument();
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("supports a sanitized error and explicit retry without losing photos", async () => {
    vi.mocked(estimatePair).mockRejectedValueOnce(new Error("sensitive internal detail"));
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(alert).toHaveTextContent("Estimate unavailable");
    expect(alert).toHaveTextContent(estimateErrorMessage(new Error("untrusted details")));
    expect(alert).not.toHaveTextContent("sensitive internal detail");
    fireEvent.click(screen.getByRole("button", { name: "Retry estimate" }));
    await screen.findByTestId("experimental-estimate-result");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(captureFrame).toHaveBeenCalledTimes(2);
  });

  it.each([-0.1, 1.1, Number.NaN, Number.POSITIVE_INFINITY])("suppresses invalid model fraction %s", async (leftoverFraction) => {
    vi.mocked(estimatePair).mockResolvedValueOnce({ ...mockEstimate, leftoverFraction });
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Estimate unavailable");
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it.each(["Retake before", "Retake after", "Clear photos"])("aborts inference and suppresses a late result after %s", async (name) => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const signal = vi.mocked(estimatePair).mock.calls[0]![2];
    fireEvent.click(screen.getByRole("button", { name }));
    expect(signal.aborted).toBe(true);
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("invalidates inference on internal step navigation", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    fireEvent.click(screen.getByRole("button", { name: /01 Before photo/ }));
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: /03 Review/ }));
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it.each(["Back to home", "Evidence", "About"])("invalidates inference before navigating through %s", async (name) => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    const link = screen.getByRole("link", { name });
    document.addEventListener("click", (event) => event.preventDefault(), { once: true });
    fireEvent.click(link);
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("cancels pending inference on a hidden tab without releasing the pair", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    const before = syntheticPhoto("hide-before"), after = syntheticPhoto("hide-after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(before.release).not.toHaveBeenCalled(); expect(after.release).not.toHaveBeenCalled();
  });

  it("clears a completed estimate on a hidden tab", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("aborts estimation and discards a late rejection after unmount", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    const view = render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    view.unmount();
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    await act(async () => { pending.reject(new Error("late worker failure")); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("cancels an estimate if starting mass changes while it is running", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "400" } });
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeEnabled();
  });

  it("aborts inference and releases photos on pagehide", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    const before = syntheticPhoto("pagehide-before"), after = syntheticPhoto("pagehide-after");
    vi.mocked(captureFrame).mockResolvedValueOnce(before).mockResolvedValueOnce(after);
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    fireEvent(window, new Event("pagehide"));
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    expect(before.release).toHaveBeenCalledOnce(); expect(after.release).toHaveBeenCalledOnce();
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it("shows no invented model crop while camera dimensions are unknown", () => {
    vi.mocked(requestCamera).mockReturnValueOnce(new Promise(() => {}));
    render(createElement(CameraCapture));
    expect(screen.queryByTestId("model-crop-frame")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    expect(screen.queryByTestId("model-crop-frame")).not.toBeInTheDocument();
  });

  it.each([
    [640, 480, 58 / 341 * 100, 6.25, 224 / 341 * 100, 87.5],
    [480, 640, 6.25, 58 / 341 * 100, 87.5, 224 / 341 * 100],
    [640, 640, 6.25, 6.25, 87.5, 87.5],
    [1280, 720, 115 / 455 * 100, 6.25, 224 / 455 * 100, 87.5],
  ])("maps known %s×%s source dimensions to the actual model crop", async (width, height, left, top, cropWidth, cropHeight) => {
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(width);
    vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(height);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take before photo" });
    const crop = screen.getByTestId("model-crop-frame");
    expect(crop).toHaveAttribute("data-source-width", String(width));
    expect(crop).toHaveAttribute("data-source-height", String(height));
    expect(Number.parseFloat(crop.style.left)).toBeCloseTo(left, 8);
    expect(Number.parseFloat(crop.style.top)).toBeCloseTo(top, 8);
    expect(Number.parseFloat(crop.style.width)).toBeCloseTo(cropWidth, 8);
    expect(Number.parseFloat(crop.style.height)).toBeCloseTo(cropHeight, 8);
    expect(screen.getByTestId("live-viewfinder").style.aspectRatio).toBe(String(width / height));
    expect(screen.getByText(/Keep all the food inside this rectangle/)).toBeInTheDocument();
  });

  it("stops unsupported dimensions safely instead of rendering an invalid crop", async () => {
    vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(16_385);
    const { stream, track } = syntheticStream();
    vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("frame dimensions cannot be prepared safely");
    expect(track.stop).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("model-crop-frame")).not.toBeInTheDocument();
    expect(captureFrame).not.toHaveBeenCalled();
  });

  it("makes the before overlay explicitly opt-in and resets it after closing the camera", async () => {
    render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    const checkbox = screen.getByRole("checkbox", { name: "Show before reference" });
    expect(checkbox).toBeDisabled(); expect(checkbox).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    expect(checkbox).toBeEnabled();
    expect(screen.queryByTestId("live-before-reference")).not.toBeInTheDocument();
    fireEvent.click(checkbox);
    expect(screen.getByTestId("live-before-reference")).toHaveStyle({ opacity: "0.35" });
    expect(checkbox).toHaveAccessibleDescription(/not automatic registration/);
    fireEvent.click(screen.getByRole("button", { name: "Close camera" }));
    expect(checkbox).toBeDisabled(); expect(checkbox).not.toBeChecked();
    expect(screen.queryByTestId("live-before-reference")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    expect(checkbox).toBeEnabled(); expect(checkbox).not.toBeChecked();
  });

  it("removes and resets the before reference when the live aspect changes beyond tolerance", async () => {
    const videoWidth = vi.spyOn(HTMLVideoElement.prototype, "videoWidth", "get").mockReturnValue(640);
    const videoHeight = vi.spyOn(HTMLVideoElement.prototype, "videoHeight", "get").mockReturnValue(480);
    const view = render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    const checkbox = screen.getByRole("checkbox", { name: "Show before reference" });
    fireEvent.click(checkbox);
    videoWidth.mockReturnValue(480); videoHeight.mockReturnValue(640);
    fireEvent(view.container.querySelector("video")!, new Event("resize"));
    expect(checkbox).toBeDisabled(); expect(checkbox).not.toBeChecked();
    expect(screen.queryByTestId("live-before-reference")).not.toBeInTheDocument();
    expect(checkbox).toHaveAccessibleDescription(/shapes differ by more than 5%/);
    expect(screen.getByTestId("model-crop-frame")).toHaveAttribute("data-source-width", "480");
    videoWidth.mockReturnValue(640); videoHeight.mockReturnValue(480);
    fireEvent(view.container.querySelector("video")!, new Event("resize"));
    expect(checkbox).toBeEnabled(); expect(checkbox).not.toBeChecked();
  });

  it("removes and resets the before reference while frames are not ready", async () => {
    const readiness = vi.spyOn(HTMLMediaElement.prototype, "readyState", "get").mockReturnValue(4);
    const view = render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Continue to after" }));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take after photo" });
    const checkbox = screen.getByRole("checkbox", { name: "Show before reference" });
    fireEvent.click(checkbox);
    readiness.mockReturnValue(0);
    fireEvent.canPlay(view.container.querySelector("video")!);
    expect(checkbox).toBeDisabled(); expect(checkbox).not.toBeChecked();
    expect(screen.queryByTestId("live-before-reference")).not.toBeInTheDocument();
    readiness.mockReturnValue(4);
    fireEvent.canPlay(view.container.querySelector("video")!);
    expect(checkbox).toBeEnabled(); expect(checkbox).not.toBeChecked();
  });

  it("lets users inspect both model crops without triggering an estimate", async () => {
    render(createElement(CameraCapture)); await pair();
    expect(screen.getByRole("button", { name: "Full photos" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryAllByTestId("model-crop-preview")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Model input" }));
    expect(screen.getByRole("button", { name: "Model input" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getAllByTestId("model-crop-preview")).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Before model input" })).toHaveAttribute("width", "224");
    expect(screen.getByRole("img", { name: "After model input" })).toHaveAttribute("height", "224");
    expect(screen.queryByRole("img", { name: "Your before photo for review" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Photo comparison view" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retake before" })).toBeEnabled();
    expect(estimatePair).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Full photos" }));
    expect(screen.queryAllByTestId("model-crop-preview")).toHaveLength(0);
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toBeInTheDocument();
  });

  it("preserves an existing estimate while switching photo inspection modes", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    fireEvent.click(screen.getByRole("button", { name: "Model input" }));
    expect(screen.getByTestId("experimental-estimate-result")).toHaveAttribute("data-leftover-fraction", "0.375");
    fireEvent.click(screen.getByRole("button", { name: "Full photos" }));
    expect(screen.getByTestId("experimental-estimate-result")).toHaveAttribute("data-leftover-fraction", "0.375");
    expect(estimatePair).toHaveBeenCalledOnce();
  });

  it("clears model inspection on retake or reset without removing the remaining retake actions", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.click(screen.getByRole("button", { name: "Model input" }));
    fireEvent.click(screen.getByRole("button", { name: "Retake after" }));
    expect(screen.queryAllByTestId("model-crop-preview")).toHaveLength(0);
    await take("after");
    fireEvent.click(screen.getByRole("button", { name: "Review & estimate" }));
    expect(screen.getByRole("button", { name: "Full photos" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Model input" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    expect(screen.queryAllByTestId("model-crop-preview")).toHaveLength(0);
    expect(screen.queryByRole("checkbox", { name: "Show before reference" })).not.toBeInTheDocument();
  });

  it("saves a before-only session only by explicit action and releases its temporary download URL", async () => {
    const before = syntheticPhoto("saved-before"); vi.mocked(captureFrame).mockResolvedValueOnce(before);
    render(createElement(CameraCapture)); await take("before");
    expect(createSessionFile).not.toHaveBeenCalled(); expect(createUrl).not.toHaveBeenCalled();
    expect(screen.getByTestId("session-controls")).toHaveTextContent("The downloaded file is unencrypted.");
    expect(screen.getByTestId("session-controls")).toHaveTextContent("Clearing this page does not delete downloaded files.");
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await waitFor(() => expect(createUrl).toHaveBeenCalledOnce());
    expect(vi.mocked(createSessionFile).mock.calls[0]![0]).toEqual({ before, after: null, startingMass: "" });
    expect(anchorClick).toHaveBeenCalledOnce();
    expect(document.querySelector('a[download]')).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save session" })).toHaveFocus());
    expect(screen.getByText(/Download requested\. Check your browser/)).toBeInTheDocument();
    expect(revokeUrl).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:session-download");
    expect(before.release).toHaveBeenCalledOnce();
  });

  it("revokes a download URL after its bounded consumption window", async () => {
    const view = render(createElement(CameraCapture)); await take("before");
    vi.useFakeTimers();
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Save session" })); await Promise.resolve(); });
    expect(revokeUrl).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:session-download");
    view.unmount(); expect(revokeUrl).toHaveBeenCalledOnce();
  });

  it("releases a download URL if the browser download click fails and preserves photos", async () => {
    anchorClick.mockImplementationOnce(() => { throw new Error("private browser detail"); });
    render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    expect(await screen.findByTestId("session-error")).toHaveTextContent("could not be processed safely");
    expect(screen.getByTestId("session-error")).not.toHaveTextContent("private browser detail");
    expect(revokeUrl).toHaveBeenCalledExactlyOnceWith("blob:session-download");
    expect(screen.getByRole("img", { name: "Your before photo" })).toBeInTheDocument();
  });

  it("cancels a pending save without starting a delayed download", async () => {
    let resolve!: (value: Blob) => void;
    vi.mocked(createSessionFile).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    render(createElement(CameraCapture)); await take("before");
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    expect(screen.getByRole("button", { name: "Cancel session operation" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Save session" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel session operation" }));
    expect(vi.mocked(createSessionFile).mock.calls[0]![1].aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Resume session" })).toHaveFocus();
    await act(async () => { resolve(new Blob(["late"])); await Promise.resolve(); });
    expect(createUrl).not.toHaveBeenCalled(); expect(anchorClick).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Your before photo" })).toBeInTheDocument();
  });

  it("saves valid mass without serializing the estimate and rejects invalid optional mass", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "-2" } });
    expect(screen.getByRole("button", { name: "Save session" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "240" } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await waitFor(() => expect(createSessionFile).toHaveBeenCalledOnce());
    expect(Object.keys(vi.mocked(createSessionFile).mock.calls[0]![0]).sort()).toEqual(["after", "before", "startingMass"]);
    expect(vi.mocked(createSessionFile).mock.calls[0]![0].startingMass).toBe("240");
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(estimatePair).toHaveBeenCalledOnce();
  });

  it("stops an open camera before the explicit session picker, even if the picker is cancelled", async () => {
    const { stream, track } = syntheticStream(); vi.mocked(requestCamera).mockResolvedValueOnce(stream);
    render(createElement(CameraCapture));
    fireEvent.click(screen.getByRole("button", { name: "Open camera" }));
    await screen.findByRole("button", { name: "Take before photo" });
    const picker = vi.spyOn(screen.getByLabelText("PlateGauge session file"), "click");
    fireEvent.click(screen.getByRole("button", { name: "Resume session" }));
    expect(track.stop).toHaveBeenCalledOnce(); expect(picker).toHaveBeenCalledOnce();
    fireEvent.change(screen.getByLabelText("PlateGauge session file"), { target: { files: [] } });
    expect(restoreSessionFile).not.toHaveBeenCalled(); expect(estimatePair).not.toHaveBeenCalled();
  });

  it.each([false, true])("restores a validated session without camera or inference (after present: %s)", async (withAfter) => {
    const restored = { ...restoredPair(), after: withAfter ? syntheticPhoto("import-after") : null };
    vi.mocked(restoreSessionFile).mockResolvedValueOnce(restored);
    const view = render(createElement(CameraCapture)); const file = chooseSession();
    await screen.findByRole("heading", { name: withAfter ? "Review the pair. Then estimate." : "Same plate. Same perspective." });
    expect(vi.mocked(restoreSessionFile).mock.calls[0]![0]).toBe(file);
    expect(screen.getByLabelText("PlateGauge session file")).toHaveValue("");
    expect(screen.queryByTestId("session-replace-confirmation")).not.toBeInTheDocument();
    expect(requestCamera).not.toHaveBeenCalled(); expect(estimatePair).not.toHaveBeenCalled();
    if (withAfter) expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("240");
    expect(restored.before.release).not.toHaveBeenCalled();
    view.unmount(); expect(restored.before.release).toHaveBeenCalledOnce();
    if (restored.after) expect(restored.after.release).toHaveBeenCalledOnce();
  });

  it("keeps the current pair and mass when a validated replacement is declined", async () => {
    const imported = restoredPair(); vi.mocked(restoreSessionFile).mockResolvedValueOnce(imported);
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "99" } });
    chooseSession(); await screen.findByTestId("session-replace-confirmation");
    await waitFor(() => expect(screen.getByRole("button", { name: "Keep current session" })).toHaveFocus());
    expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("99");
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toHaveAttribute("src", "blob:generated-1");
    fireEvent.click(screen.getByRole("button", { name: "Keep current session" }));
    expect(imported.before.release).toHaveBeenCalledOnce(); expect(imported.after.release).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: "Resume session" })).toHaveFocus();
    expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("99");
    expect(estimatePair).not.toHaveBeenCalled();
  });

  it("adopts imported photos only after consent and releases replaced photos once", async () => {
    const oldBefore = syntheticPhoto("old-before"); const oldAfter = syntheticPhoto("old-after");
    vi.mocked(captureFrame).mockResolvedValueOnce(oldBefore).mockResolvedValueOnce(oldAfter);
    const imported = restoredPair(); vi.mocked(restoreSessionFile).mockResolvedValueOnce(imported);
    const view = render(createElement(CameraCapture)); await pair(); chooseSession();
    await screen.findByTestId("session-replace-confirmation");
    expect(oldBefore.release).not.toHaveBeenCalled(); expect(oldAfter.release).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Replace current session" }));
    expect(oldBefore.release).toHaveBeenCalledOnce(); expect(oldAfter.release).toHaveBeenCalledOnce();
    expect(imported.before.release).not.toHaveBeenCalled(); expect(imported.after.release).not.toHaveBeenCalled();
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toHaveAttribute("src", imported.before.url);
    expect(screen.getByRole("heading", { name: "Review the pair. Then estimate." })).toHaveFocus();
    expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("240");
    expect(estimatePair).not.toHaveBeenCalled(); expect(requestCamera).toHaveBeenCalledTimes(2);
    view.unmount(); expect(imported.before.release).toHaveBeenCalledOnce(); expect(imported.after.release).toHaveBeenCalledOnce();
    expect(oldBefore.release).toHaveBeenCalledOnce();
  });

  it("preserves the current pair and mass on invalid import and suppresses stale estimates", async () => {
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    vi.mocked(restoreSessionFile).mockRejectedValueOnce(new Error("private filename and file contents"));
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "99" } });
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    chooseSession();
    expect(vi.mocked(estimatePair).mock.calls[0]![2].aborted).toBe(true);
    const sessionError = await screen.findByTestId("session-error");
    await waitFor(() => expect(sessionError).toHaveFocus());
    expect(screen.getByTestId("session-error")).not.toHaveTextContent("private filename");
    expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("99");
    expect(screen.getByRole("img", { name: "Your before photo for review" })).toHaveAttribute("src", "blob:generated-1");
    expect(screen.queryByTestId("session-replace-confirmation")).not.toBeInTheDocument();
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
  });

  it.each(["cancel", "clear", "retake", "navigate", "mass", "hidden", "pagehide", "unmount"] as const)("aborts and releases a late import after %s", async (action) => {
    const pending = deferredSession(); vi.mocked(restoreSessionFile).mockReturnValueOnce(pending.promise);
    const imported = restoredPair();
    const view = render(createElement(CameraCapture)); await pair(); chooseSession();
    const signal = vi.mocked(restoreSessionFile).mock.calls[0]![1];
    if (action === "cancel") fireEvent.click(screen.getByRole("button", { name: "Cancel session operation" }));
    if (action === "clear") fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    if (action === "retake") fireEvent.click(screen.getByRole("button", { name: "Retake after" }));
    if (action === "navigate") fireEvent.click(screen.getByRole("button", { name: /01 Before photo/ }));
    if (action === "mass") fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "51" } });
    if (action === "hidden") { vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden"); fireEvent(document, new Event("visibilitychange")); }
    if (action === "pagehide") fireEvent(window, new Event("pagehide"));
    if (action === "unmount") view.unmount();
    expect(signal.aborted).toBe(true);
    await act(async () => { pending.resolve(imported); await Promise.resolve(); });
    expect(imported.before.release).toHaveBeenCalledOnce(); expect(imported.after.release).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("session-replace-confirmation")).not.toBeInTheDocument();
    expect(screen.queryByTestId("experimental-estimate-result")).not.toBeInTheDocument();
    expect(estimatePair).not.toHaveBeenCalled();
  });

  it.each(["hidden", "clear", "mass", "unmount"] as const)("releases a validated but unaccepted replacement on %s", async (action) => {
    const imported = restoredPair(); vi.mocked(restoreSessionFile).mockResolvedValueOnce(imported);
    const view = render(createElement(CameraCapture)); await pair(); chooseSession();
    await screen.findByTestId("session-replace-confirmation");
    if (action === "hidden") { vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden"); fireEvent(document, new Event("visibilitychange")); }
    if (action === "clear") fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    if (action === "mass") fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "51" } });
    if (action === "unmount") view.unmount();
    expect(imported.before.release).toHaveBeenCalledOnce(); expect(imported.after.release).toHaveBeenCalledOnce();
    expect(screen.queryByTestId("session-replace-confirmation")).not.toBeInTheDocument();
    if (action === "hidden" || action === "mass") expect(screen.getByRole("img", { name: "Your before photo for review" })).toHaveAttribute("src", "blob:generated-1");
  });

  it("supports a mocked codec round trip without resuming predictions", async () => {
    render(createElement(CameraCapture)); await pair();
    fireEvent.change(screen.getByLabelText("Starting food mass (g, optional)"), { target: { value: "125.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save session" }));
    await waitFor(() => expect(createUrl).toHaveBeenCalledOnce());
    const saved = vi.mocked(createSessionFile).mock.calls[0]![0];
    fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    vi.mocked(restoreSessionFile).mockResolvedValueOnce({ before: syntheticPhoto("roundtrip-before"), after: saved.after ? syntheticPhoto("roundtrip-after") : null, startingMass: saved.startingMass });
    chooseSession(); await screen.findByRole("heading", { name: "Review the pair. Then estimate." });
    expect(screen.getByLabelText("Starting food mass (g, optional)")).toHaveValue("125.5");
    expect(screen.getByRole("button", { name: "Estimate remaining" })).toBeEnabled();
    expect(estimatePair).not.toHaveBeenCalled(); expect(requestCamera).toHaveBeenCalledTimes(2);
  });

  it("passes only present-state flags and successful timing observations to the diagnostic panel", async () => {
    const observations = () => JSON.parse(screen.getByTestId("device-check-observations").getAttribute("data-observations")!) as DeviceObservations;
    render(createElement(CameraCapture));
    expect(observations()).toEqual({ cameraReadyNow: false, beforePresent: false, afterPresent: false, latestCaptureMs: null, latestEstimateWallMs: null, latestModelProcessingMs: null });
    await pair();
    expect(observations().latestCaptureMs).toEqual(expect.any(Number));
    expect(Number.isFinite(observations().latestCaptureMs)).toBe(true);
    expect(observations().latestEstimateWallMs).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    await screen.findByTestId("experimental-estimate-result");
    expect(observations().latestEstimateWallMs).toEqual(expect.any(Number));
    expect(Number.isFinite(observations().latestEstimateWallMs)).toBe(true);
    expect(observations().latestModelProcessingMs).toBe(12.5);
    const restored = restoredPair(); vi.mocked(restoreSessionFile).mockResolvedValueOnce(restored); chooseSession();
    await screen.findByTestId("session-replace-confirmation");
    fireEvent.click(screen.getByRole("button", { name: "Replace current session" }));
    expect(observations()).toEqual({ cameraReadyNow: false, beforePresent: true, afterPresent: true, latestCaptureMs: null, latestEstimateWallMs: null, latestModelProcessingMs: null });
    const pending = deferredEstimate(); vi.mocked(estimatePair).mockReturnValueOnce(pending.promise);
    fireEvent.click(screen.getByRole("button", { name: "Estimate remaining" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel estimate" }));
    await act(async () => { pending.resolve(mockEstimate); await Promise.resolve(); });
    expect(observations().latestEstimateWallMs).toBeNull(); expect(observations().latestModelProcessingMs).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear photos" }));
    expect(observations()).toEqual({ cameraReadyNow: false, beforePresent: false, afterPresent: false, latestCaptureMs: null, latestEstimateWallMs: null, latestModelProcessingMs: null });
  });
});
