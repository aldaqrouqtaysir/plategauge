import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import {
  absoluteError,
  categoryComparisons,
  benchmarkExamples,
  engineeringEvidence,
  endpointPrevalence,
  exampleAssetUrl,
  frozenMetrics,
  robustnessSummary,
  targetSliceMetrics,
  workloadEvidence,
  type BenchmarkExample,
  type BenchmarkExampleKind,
} from "./benchmarkData";
import { inspectImage, validatePair } from "./lib/imageValidation";
import { ModelClient } from "./lib/modelClient";
import { prepareImage } from "./lib/preprocess";
import type { InspectedImage, ModelState } from "./types";
import { ModelError } from "./types";

const DEFAULT_EXAMPLE: BenchmarkExample = benchmarkExamples[0]!;
const DEFAULT_SELECTED_ID = "lefood-0192";
const FIXED_REPLAY_TIMEOUT_MS = 15_000;
const sourceUrl = import.meta.env.VITE_SOURCE_URL;

function Icon({ children, size = 20 }: { children: ReactNode; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {children}
    </svg>
  );
}

const ArrowIcon = () => (
  <Icon size={18}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </Icon>
);

const CheckIcon = () => (
  <Icon size={17}>
    <path d="m5 12 4 4L19 6" />
  </Icon>
);

const WarningIcon = () => (
  <Icon size={22}>
    <path d="M12 3 2.8 19h18.4L12 3Z" />
    <path d="M12 9v4M12 16.5h.01" />
  </Icon>
);

function percent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function percentagePoints(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)} pp`;
}

function signedPoints(value: number): string {
  const points = value * 100;
  return `${points >= 0 ? "+" : ""}${points.toFixed(2)} percentage points`;
}

function kindLabel(kind: BenchmarkExampleKind): string {
  return kind === "representative_success" ? "Selected success" : "Largest error";
}

interface FixedAssets {
  before: InspectedImage;
  after: InspectedImage;
}

type AssetState =
  | { status: "loading"; sampleId: string }
  | { status: "ready"; sampleId: string; assets: FixedAssets }
  | { status: "error"; sampleId: string; message: string };

interface ReplayBinding {
  readonly sampleId: string;
  readonly replayId: number;
}

type ReplayState =
  | { status: "idle" }
  | { status: "running"; binding: ReplayBinding }
  | {
      status: "complete";
      binding: ReplayBinding;
      processingMs: number;
      modelVersion: string;
      isTestAdapter: boolean;
    }
  | { status: "error"; binding: ReplayBinding; message: string };

async function loadFixedAsset(url: string, name: string): Promise<InspectedImage> {
  const response = await fetch(url, { cache: "force-cache", credentials: "same-origin" });
  if (!response.ok) throw new Error(`Bundled example image is unavailable (${response.status}).`);
  const blob = await response.blob();
  const file = new File([blob], name, { type: blob.type || "image/jpeg" });
  return inspectImage(file);
}

function ModelStatus({ state }: { state: ModelState }) {
  if (state.status === "loading") {
    return (
      <div className="model-status loading" role="status">
        <span className="status-dot" /> Loading the frozen browser model for fixed-pair replay…
      </div>
    );
  }
  if (state.status === "unavailable") {
    return (
      <div className="model-status unavailable" role="alert">
        <span className="status-dot" />
        <span>
          <strong>Replay unavailable.</strong> {state.message} The frozen benchmark records remain
          viewable below.
        </span>
      </div>
    );
  }
  return (
    <div
      className={`model-status ready ${state.isTestAdapter ? "test-adapter" : ""}`}
      role="status"
      data-testid="model-ready"
      data-model-version={state.modelVersion}
      data-test-adapter={state.isTestAdapter ? "true" : "false"}
    >
      <span className="status-dot" />
      <span>
        {state.isTestAdapter ? (
          <>
            <strong>Test adapter active.</strong> Replay output is synthetic and never benchmark
            evidence.
          </>
        ) : (
          <>
            <strong>Frozen model ready.</strong> Version {state.modelVersion}. Replay is limited to
            bundled examples.
          </>
        )}
      </span>
    </div>
  );
}

function MetricCard({ value, label, detail }: { value: string; label: string; detail: string }) {
  return (
    <article className="metric-card">
      <strong>{value}</strong>
      <h3>{label}</h3>
      <p>{detail}</p>
    </article>
  );
}

function ExampleChooser({
  kind,
  selectedId,
  onSelect,
}: {
  kind: BenchmarkExampleKind;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const examples = benchmarkExamples.filter((example) => example.kind === kind);
  return (
    <section className="chooser-group" aria-labelledby={`${kind}-title`}>
      <div className="chooser-heading">
        <h3 id={`${kind}-title`}>
          {kind === "representative_success" ? "Five selected successes" : "Five largest errors"}
        </h3>
        <p>
          {kind === "representative_success"
            ? "Hand-picked to span the target range—not a random sample."
            : "Ranked by absolute paired-model error across all 514 outer-fold predictions."}
        </p>
      </div>
      <div className="example-buttons">
        {examples.map((example) => (
          <button
            type="button"
            key={example.id}
            className={selectedId === example.id ? "selected" : ""}
            role="radio"
            aria-checked={selectedId === example.id}
            aria-controls="selected-example-panel"
            tabIndex={selectedId === example.id ? 0 : -1}
            onClick={() => onSelect(example.id)}
            data-testid={`example-${example.id}`}
          >
            <span>{kind === "largest_error" ? `#${example.rank}` : `${example.rank}`}</span>
            <strong>{example.id.replace("lefood-", "")}</strong>
            <small>
              {percentagePoints(absoluteError(example.pairedPrediction, example.target))} error
            </small>
          </button>
        ))}
      </div>
    </section>
  );
}

function moveExampleSelection(event: KeyboardEvent<HTMLElement>) {
  const supportedKeys = ["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"];
  if (!supportedKeys.includes(event.key)) return;

  const current = (event.target as HTMLElement).closest<HTMLButtonElement>('[role="radio"]');
  if (!current) return;
  const options = Array.from(
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]'),
  );
  const currentIndex = options.indexOf(current);
  if (currentIndex < 0 || options.length === 0) return;

  event.preventDefault();
  let nextIndex = currentIndex;
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = options.length - 1;
  if (event.key === "ArrowDown" || event.key === "ArrowRight") {
    nextIndex = (currentIndex + 1) % options.length;
  }
  if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
    nextIndex = (currentIndex - 1 + options.length) % options.length;
  }

  const next = options[nextIndex];
  next?.focus();
  next?.click();
}

function EvidenceBar({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className="evidence-row">
      <div className="evidence-label">
        <span>{label}</span>
        <strong>{percent(value)}</strong>
      </div>
      <div className="evidence-track" aria-hidden="true">
        <span className={tone} style={{ width: `${Math.max(1, value * 100)}%` }} />
      </div>
    </div>
  );
}

function FrozenExample({ example }: { example: BenchmarkExample }) {
  const [failedImageRoles, setFailedImageRoles] = useState<Array<"before" | "after">>([]);

  const imageFailed = (role: "before" | "after") => {
    setFailedImageRoles((current) =>
      current.includes(role) ? current : [...current, role],
    );
  };

  return (
    <article
      className={`example-detail ${example.kind}`}
      id="selected-example-panel"
      aria-labelledby="selected-example-title"
    >
      <div className="example-meta">
        <span className="evidence-badge">
          {kindLabel(example.kind)} · {example.kind === "largest_error" ? `rank ${example.rank}` : `set ${example.rank}`}
        </span>
        <span>Historical held-out record—not a new estimate</span>
        <span>Outer fold {example.fold} · category {example.category}</span>
      </div>
      <div className="example-title-row">
        <div>
          <p className="eyebrow">Frozen record {example.id}</p>
          <h3 id="selected-example-title">{example.foodName}</h3>
        </div>
        <div
          className="mass-equation"
          aria-label={`${example.afterMassG} grams after divided by ${example.beforeMassG} grams before`}
        >
          <span>{example.afterMassG} g after</span><b>÷</b><span>{example.beforeMassG} g before</span><b>=</b><strong>{percent(example.target)}</strong>
        </div>
      </div>

      <div className="image-pair" data-testid="fixed-image-pair">
        <figure>
          <div className="image-frame">
            {failedImageRoles.includes("before") ? (
              <div className="fixed-image-placeholder" aria-hidden="true">Before image unavailable</div>
            ) : (
              <img
                src={exampleAssetUrl(example.id, "before")}
                alt={`Before photograph for LeFood sample ${example.id}`}
                onError={() => imageFailed("before")}
              />
            )}
          </div>
          <figcaption><span>Before</span><strong>{example.beforeMassG} g</strong></figcaption>
        </figure>
        <div className="pair-arrow" aria-hidden="true"><ArrowIcon /></div>
        <figure>
          <div className="image-frame">
            {failedImageRoles.includes("after") ? (
              <div className="fixed-image-placeholder" aria-hidden="true">After image unavailable</div>
            ) : (
              <img
                src={exampleAssetUrl(example.id, "after")}
                alt={`After photograph for LeFood sample ${example.id}`}
                onError={() => imageFailed("after")}
              />
            )}
          </div>
          <figcaption><span>After</span><strong>{example.afterMassG} g</strong></figcaption>
        </figure>
      </div>
      {failedImageRoles.length > 0 ? (
        <div className="inline-alert fixed-image-alert" role="alert" data-testid="fixed-image-error">
          One or more licensed example images could not be displayed. No substitute image was
          used; the frozen numeric record remains visible for inspection.
        </div>
      ) : null}

      <div className="evidence-comparison" aria-label="Frozen prediction comparison">
        <EvidenceBar label="Measured target" value={example.target} tone="target" />
        <EvidenceBar label="Paired MobileNet" value={example.pairedPrediction} tone="paired" />
        <EvidenceBar label="After-only MobileNet" value={example.afterOnlyPrediction} tone="after-only" />
      </div>
      <div className="error-summary">
        <span>
          Paired absolute error{" "}
          <strong>{percentagePoints(absoluteError(example.pairedPrediction, example.target))}</strong>
        </span>
        <span>
          After-only absolute error{" "}
          <strong>
            {percentagePoints(absoluteError(example.afterOnlyPrediction, example.target))}
          </strong>
        </span>
      </div>
      <p className="review-note">
        <WarningIcon />
        <span>
          <strong>AI-assisted post-hoc review hypothesis.</strong> {example.note}
        </span>
      </p>
    </article>
  );
}

function TargetSlicePanel() {
  const maxMae = Math.max(...targetSliceMetrics.map((slice) => slice.microMae));
  return (
    <article className="evidence-panel slice-panel" aria-labelledby="slice-panel-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Where error concentrated</p>
          <h3 id="slice-panel-title">Target-range errors</h3>
        </div>
        <p>Micro MAE · lower is better</p>
      </div>
      <div className="slice-list">
        {targetSliceMetrics.map((slice) => (
          <div className="slice-row" key={slice.label}>
            <div className="slice-label">
              <span>{slice.label}</span>
              <small>n={slice.count}</small>
              <strong>{percentagePoints(slice.microMae, 2)}</strong>
            </div>
            <div className="slice-track" aria-hidden="true">
              <span style={{ width: `${(slice.microMae / maxMae) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
      <p className="panel-boundary">
        {endpointPrevalence.endpointTotal} of {endpointPrevalence.total} targets ({percent(
          endpointPrevalence.endpointFraction,
          1,
        )}) are exact zero or one; the remaining {endpointPrevalence.interior} are interior values.
        Boundary prevalence can make aggregate error look better than interior performance. <br />
        The highest broad-slice error was{" "}
        {percentagePoints(frozenMetrics.worstBroadTargetSliceMicroMae, 2)} in (0.50, 0.75].
        These errors show where performance deteriorated—not broad-slice validity.
      </p>
    </article>
  );
}

function workloadRole(role: string): string {
  switch (role) {
    case "contextual_reference":
      return "context only";
    case "required_ablation":
      return "required ablation";
    case "primary_confirmatory_model":
      return "primary model";
    case "destructive_mismatch_control":
      return "destructive mismatch";
    case "non_neural_baseline":
      return "non-neural baseline";
    default:
      return "comparison";
  }
}

function WorkloadComparisonPanel() {
  const maxMae = Math.max(
    ...workloadEvidence.records.map((record) => record.macroCategoryMae),
  );
  return (
    <article className="evidence-panel comparison-panel" aria-labelledby="comparison-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Complete comparison set</p>
          <h3 id="comparison-title">Every frozen workload, not only the favorable ones.</h3>
        </div>
        <p>Macro-category MAE · lower is better</p>
      </div>
      <div className="comparison-list">
        {workloadEvidence.records.map((record) => (
          <div className={`comparison-row ${record.role}`} key={record.id}>
            <div className="comparison-name">
              <strong>{record.label}</strong>
              <span>{workloadRole(record.role)}</span>
              <small>{record.caveat}</small>
            </div>
            <div className="comparison-measure">
              <div className="comparison-track" aria-hidden="true">
                <span style={{ width: `${(record.macroCategoryMae / maxMae) * 100}%` }} />
              </div>
              <strong>{percentagePoints(record.macroCategoryMae, 2)}</strong>
            </div>
          </div>
        ))}
      </div>
      <p className="panel-boundary">
        The observer score is contextual—not an image-only deployable model. The wrong-pair run
        destroys the target-linked after image during training and evaluation; its poor score does
        not show that the before image adds incremental value.
      </p>
    </article>
  );
}

function CategoryComparisonPanel() {
  const pairedBetter = categoryComparisons.filter(
    (record) => record.pairedMinusAfterOnly < 0,
  ).length;
  const afterOnlyBetter = categoryComparisons.filter(
    (record) => record.pairedMinusAfterOnly > 0,
  ).length;
  const tied = categoryComparisons.length - pairedBetter - afterOnlyBetter;
  return (
    <article className="evidence-panel category-panel" aria-labelledby="category-panel-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Category-level evidence</p>
          <h3 id="category-panel-title">The aggregate result was not uniform.</h3>
        </div>
      </div>
      <div className="category-summary" aria-label="Category comparison summary">
        <span><strong>{afterOnlyBetter}</strong> categories favored after-only</span>
        <span><strong>{pairedBetter}</strong> favored paired</span>
        {tied > 0 ? <span><strong>{tied}</strong> tied</span> : null}
      </div>
      <details className="category-details">
        <summary>Inspect all 34 categories and support counts</summary>
        <div className="category-table-wrap">
          <table>
            <caption>
              Positive differences mean the paired model had higher error. Small-support rows are
              descriptive and unstable.
            </caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col">n</th>
                <th scope="col">Paired MAE</th>
                <th scope="col">After-only MAE</th>
                <th scope="col">Paired − after-only</th>
              </tr>
            </thead>
            <tbody>
              {categoryComparisons.map((record) => (
                <tr key={record.category}>
                  <th scope="row">{record.category}</th>
                  <td>{record.support}</td>
                  <td>{percentagePoints(record.pairedMae, 2)}</td>
                  <td>{percentagePoints(record.afterOnlyMae, 2)}</td>
                  <td className={record.pairedMinusAfterOnly > 0 ? "delta-worse" : "delta-better"}>
                    {signedPoints(record.pairedMinusAfterOnly)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <p className="panel-boundary">
        These are the 34 evaluated image categories 000–033. Workbook-only categories 034–049 had
        no archived images and are not represented by this benchmark.
      </p>
    </article>
  );
}

function RobustnessPanel() {
  const clean = robustnessSummary.records.find((record) => record.id === "clean")!;
  const blur = robustnessSummary.records.find(
    (record) => record.id === "after_gaussian_blur_sigma_1",
  )!;
  const misuse = robustnessSummary.records.filter((record) => record.role === "misuse_test");
  return (
    <article className="evidence-panel robustness-panel" aria-labelledby="robustness-title">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Robustness boundary</p>
          <h3 id="robustness-title">A routine blur breached the frozen limit.</h3>
        </div>
      </div>
      <div className="robustness-comparison">
        <div>
          <span>Clean all-data model</span>
          <strong>{percentagePoints(clean.macroCategoryMae, 2)}</strong>
        </div>
        <div className="breach">
          <span>After-image blur σ=1</span>
          <strong>{percentagePoints(blur.macroCategoryMae, 2)}</strong>
          <small>{signedPoints(blur.deltaFromClean)} vs. clean; 3.00-point gate breached</small>
        </div>
      </div>
      <div className="misuse-grid" aria-label="Misuse diagnostics">
        {misuse.map((record) => (
          <div key={record.id}>
            <span>{record.label}</span>
            <strong>{percentagePoints(record.macroCategoryMae, 2)}</strong>
          </div>
        ))}
      </div>
      <p className="panel-boundary">
        {robustnessSummary.caveat} The failed routine-perturbation gate blocks a robustness claim;
        misuse rows illustrate failure behavior rather than field validity.
      </p>
    </article>
  );
}

function EngineeringPanel() {
  return (
    <article
      className="evidence-panel engineering-panel"
      id="engineering"
      aria-labelledby="engineering-title"
    >
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Artifact-specific engineering evidence</p>
          <h3 id="engineering-title">A compact, browser-checked candidate.</h3>
        </div>
      </div>
      <dl className="engineering-grid">
        <div>
          <dt>FP32 ONNX</dt>
          <dd>
            <span>10.36 MB</span>
            <small>{engineeringEvidence.modelBytes.toLocaleString("en-US")} bytes</small>
          </dd>
        </div>
        <div>
          <dt>PyTorch ↔ ONNX drift</dt>
          <dd>
            <span>5.19 × 10<sup>−6</sup></span>
            <small>Maximum across eight frozen samples</small>
          </dd>
        </div>
        <div>
          <dt>Warm browser p95</dt>
          <dd>
            <span>{engineeringEvidence.warmP95Ms.toFixed(2)} ms</span>
            <small>20 runs after three warm-ups</small>
          </dd>
        </div>
        <div>
          <dt>Peak app memory</dt>
          <dd>
            <span>{engineeringEvidence.peakMemoryMiB.toFixed(2)} MiB</span>
            <small>Measured reference environment only</small>
          </dd>
        </div>
      </dl>
      <p className="panel-boundary">
        Browser measurements come from one documented HP laptop running headed Chrome 152. They
        do not support phone, unmeasured-browser, production, or field-performance claims.
      </p>
    </article>
  );
}

export default function App() {
  const benchmarkMode = useMemo(
    () => new URLSearchParams(window.location.search).get("benchmark") === "1",
    [],
  );
  const [selectedId, setSelectedId] = useState(DEFAULT_SELECTED_ID);
  const [modelState, setModelState] = useState<ModelState>({ status: "loading" });
  const [assetState, setAssetState] = useState<AssetState>({
    status: "loading",
    sampleId: DEFAULT_SELECTED_ID,
  });
  const [replay, setReplay] = useState<ReplayState>({ status: "idle" });
  const clientRef = useRef<ModelClient | null>(null);
  const replayAbortRef = useRef<AbortController | null>(null);
  const activeReplayRef = useRef<ReplayBinding | null>(null);
  const replaySequenceRef = useRef(0);
  const selected = useMemo(
    () => benchmarkExamples.find((example) => example.id === selectedId) ?? DEFAULT_EXAMPLE,
    [selectedId],
  );

  const cancelActiveReplay = useCallback((resetState = true) => {
    replayAbortRef.current?.abort();
    replayAbortRef.current = null;
    activeReplayRef.current = null;
    if (resetState) setReplay({ status: "idle" });
  }, []);

  const selectExample = useCallback(
    (id: string) => {
      if (id === selectedId) return;
      cancelActiveReplay();
      setSelectedId(id);
    },
    [cancelActiveReplay, selectedId],
  );

  useEffect(() => {
    if (!benchmarkMode) return undefined;
    const client = new ModelClient();
    clientRef.current = client;
    const initialization = new AbortController();
    let active = true;
    void client.initialize({ signal: initialization.signal }).then(
      (state) => {
        if (active) setModelState(state);
      },
      (error: unknown) => {
        if (!active || initialization.signal.aborted) return;
        const message = error instanceof ModelError
          ? error.message
          : "The frozen browser model could not be initialized.";
        setModelState({ status: "unavailable", message });
      },
    );
    return () => {
      active = false;
      initialization.abort();
      cancelActiveReplay(false);
      client.dispose();
      clientRef.current = null;
    };
  }, [benchmarkMode, cancelActiveReplay]);

  useEffect(() => {
    if (!benchmarkMode) return undefined;
    const sampleId = selected.id;
    cancelActiveReplay();
    let active = true;
    setAssetState({ status: "loading", sampleId });
    void Promise.all([
      loadFixedAsset(exampleAssetUrl(sampleId, "before"), `${sampleId}-before.jpg`),
      loadFixedAsset(exampleAssetUrl(sampleId, "after"), `${sampleId}-after.jpg`),
    ]).then(
      ([before, after]) => {
        if (!active) return;
        try {
          validatePair(before, after);
          setAssetState({ status: "ready", sampleId, assets: { before, after } });
        } catch (error) {
          setAssetState({
            status: "error",
            sampleId,
            message: error instanceof Error ? error.message : "The bundled pair is invalid.",
          });
        }
      },
      (error: unknown) => {
        if (!active) return;
        setAssetState({
          status: "error",
          sampleId,
          message: error instanceof Error ? error.message : "The bundled pair could not be loaded.",
        });
      },
    );
    return () => {
      active = false;
    };
  }, [benchmarkMode, cancelActiveReplay, selected.id]);

  const runFixedReplay = async () => {
    const client = clientRef.current;
    if (
      assetState.status !== "ready" ||
      assetState.sampleId !== selected.id ||
      modelState.status !== "ready" ||
      !client
    ) return;

    cancelActiveReplay(false);
    const controller = new AbortController();
    const binding: ReplayBinding = {
      sampleId: selected.id,
      replayId: replaySequenceRef.current + 1,
    };
    replaySequenceRef.current = binding.replayId;
    replayAbortRef.current = controller;
    activeReplayRef.current = binding;
    setReplay({ status: "running", binding });

    const isCurrent = (candidate: ReplayBinding): boolean => {
      const active = activeReplayRef.current;
      return (
        active?.sampleId === candidate.sampleId && active.replayId === candidate.replayId
      );
    };

    try {
      const [before, after] = await Promise.all([
        prepareImage(assetState.assets.before),
        prepareImage(assetState.assets.after),
      ]);
      if (controller.signal.aborted || !isCurrent(binding)) return;

      const response = await client.predictBound(binding, before, after, {
        signal: controller.signal,
        timeoutMs: FIXED_REPLAY_TIMEOUT_MS,
      });
      if (
        controller.signal.aborted ||
        response.binding.sampleId !== binding.sampleId ||
        response.binding.replayId !== binding.replayId ||
        !isCurrent(response.binding)
      ) return;

      const result = response.result;
      setReplay({
        status: "complete",
        binding: response.binding,
        processingMs: result.processingMs,
        modelVersion: result.modelVersion,
        isTestAdapter: result.isTestAdapter,
      });
    } catch (error: unknown) {
      if (controller.signal.aborted || !isCurrent(binding)) return;
      const message =
        error instanceof Error ? error.message : "The fixed replay could not finish.";
      setReplay({
        status: "error",
        binding,
        message,
      });
      if (
        error instanceof ModelError &&
        ["MODEL_REQUEST_TIMEOUT", "MODEL_CLIENT_DISPOSED", "WORKER_ERROR"].includes(error.code)
      ) {
        setModelState({ status: "unavailable", message });
      }
    } finally {
      if (isCurrent(binding)) {
        replayAbortRef.current = null;
        activeReplayRef.current = null;
      }
    }
  };

  const replayReady =
    assetState.status === "ready" &&
    assetState.sampleId === selected.id &&
    modelState.status === "ready";

  return (
    <>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="PlateGauge benchmark explorer home">
          <span className="brand-mark" aria-hidden="true"><span /></span><span>PlateGauge</span>
        </a>
        <nav aria-label="Primary navigation">
          <a href="#results">Results</a>
          <a href="#explorer" aria-label="Evidence explorer">
            <span className="nav-label-wide">Evidence explorer</span>
            <span className="nav-label-compact">Evidence</span>
          </a>
          <a href="#engineering">Engineering</a>
          <a href="#limits">Limits</a>
        </nav>
        <div className="release-pill">
          <span className="release-label-wide">PlateGauge v1.0.2 · benchmark and failure explorer</span>
          <span className="release-label-compact">v1.0.2 · benchmark explorer</span>
        </div>
      </header>

      <main id="main" tabIndex={-1}>
        <section className="hero" id="top">
          <div className="hero-copy">
            <p className="eyebrow">A benchmark-only category-shift computer-vision study</p>
            <h1>Explore the result—<br /><em>including where it failed.</em></h1>
            <p className="hero-lead">
              PlateGauge tested whether a before-and-after image pair improves leftover-fraction
              estimation on unseen food categories. The paired model beat the best non-neural
              baseline, but an after-image-only model performed better.
            </p>
            <div className="hero-actions">
              <a className="primary-link" href="#explorer">Inspect frozen examples <ArrowIcon /></a>
              <a className="secondary-link" href="#results">Read headline results</a>
            </div>
            <ul className="trust-row" aria-label="Study principles">
              <li><CheckIcon /> Frozen outer-fold evidence</li>
              <li><CheckIcon /> Negative result reported</li>
              <li><CheckIcon /> Fixed licensed examples</li>
            </ul>
          </div>
          <aside className="finding-card" aria-label="Primary finding">
            <span>Primary paired model</span>
            <strong>{percentagePoints(frozenMetrics.pairedMacroMae, 2)}</strong>
            <p>macro-category mean absolute error</p>
            <div className="finding-divider" />
            <span>After-only comparator</span>
            <strong>{percentagePoints(frozenMetrics.afterOnlyMacroMae, 2)}</strong>
            <p>macro-category mean absolute error · lower is better</p>
            <div className="negative-finding">Paired was {signedPoints(frozenMetrics.pairedMinusAfterOnly)} worse.</div>
          </aside>
        </section>

        <section className="results-section" id="results" aria-labelledby="results-title">
          <div className="section-heading">
            <div><p className="eyebrow">Frozen confirmatory evaluation</p><h2 id="results-title">The paired model did not outperform after-only.</h2></div>
            <p>Five category-disjoint outer folds evaluated all {frozenMetrics.validPairs} valid LeFood pairs across {frozenMetrics.categories} categories once.</p>
          </div>
          <p className="target-definition">
            <strong>What is measured:</strong> leftover fraction = recorded after mass ÷ recorded
            before mass. A target of 0 means none of the recorded mass remained; 1 means all of it
            remained. MAE is reported as absolute error in percentage points, not model accuracy.
          </p>
          <div className="metrics-grid">
            <MetricCard value={percentagePoints(frozenMetrics.pairedMacroMae, 2)} label="Paired macro MAE" detail="Primary metric across 34 category-level MAEs." />
            <MetricCard value={percentagePoints(frozenMetrics.afterOnlyMacroMae, 2)} label="After-only macro MAE" detail="Better than the paired model by 2.49 percentage points." />
            <MetricCard value={percentagePoints(frozenMetrics.pairedP90AbsoluteError, 2)} label="90th-percentile error" detail="One in ten paired-model errors was at least this large." />
            <MetricCard value={percent(frozenMetrics.pairedWithinTenPoints, 1)} label="Within ±10 points" detail="Fraction of all 514 paired-model predictions within this tolerance." />
          </div>
          <div className="result-callout">
            <WarningIcon />
            <p>
              <strong>The intended paired advantage did not materialize.</strong> Paired minus after-only macro MAE was {signedPoints(frozenMetrics.pairedMinusAfterOnly)}; the paired category-bootstrap 95% interval was {signedPoints(frozenMetrics.pairedMinusAfterOnlyCi95[0]!)} to {signedPoints(frozenMetrics.pairedMinusAfterOnlyCi95[1]!)}. That interval is conditional on the frozen split, seed, trained models, and observed categories—not full retraining or deployment uncertainty. The public outcome is therefore a benchmark and failure explorer, not an unrestricted estimator.
            </p>
          </div>
          <div className="evidence-download">
            <div>
              <strong>Audit the browser evidence directly.</strong>
              <span>
                Compact JSON derived from 18 hash-bound frozen sources; no raw images or source
                workbook are included.
              </span>
            </div>
            <a
              href={`${import.meta.env.BASE_URL}evidence/benchmark-evidence.json`}
              download="plategauge-benchmark-evidence.json"
            >
              Download evidence JSON <ArrowIcon />
            </a>
          </div>
          <div className="evidence-panels">
            <WorkloadComparisonPanel />
            <CategoryComparisonPanel />
            <TargetSlicePanel />
            <RobustnessPanel />
            <EngineeringPanel />
          </div>
        </section>

        <section className="explorer-section" id="explorer" aria-labelledby="explorer-title">
          <div className="section-heading">
            <div><p className="eyebrow">Fixed evidence explorer</p><h2 id="explorer-title">Look at both the close predictions and the hard failures.</h2></div>
            <p>These ten records are disclosed selections from frozen outer-fold predictions. Uploads are disabled; you cannot obtain a result for a new image.</p>
          </div>
          <div className="explorer-layout">
            <aside
              className="example-chooser"
              role="radiogroup"
              aria-label="Choose one frozen benchmark example"
              onKeyDown={moveExampleSelection}
            >
              <ExampleChooser kind="representative_success" selectedId={selected.id} onSelect={selectExample} />
              <ExampleChooser kind="largest_error" selectedId={selected.id} onSelect={selectExample} />
            </aside>
            <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
              Selected {selected.foodName}, {kindLabel(selected.kind).toLowerCase()}, paired absolute
              error {percentagePoints(absoluteError(selected.pairedPrediction, selected.target))}.
            </p>
            <FrozenExample key={selected.id} example={selected} />
          </div>

          {benchmarkMode ? <section className="replay-panel" aria-labelledby="replay-title" data-testid="benchmark-harness">
            <div className="replay-copy">
              <p className="eyebrow">Unlinked benchmark harness</p>
              <h3 id="replay-title">Measure one fixed browser inference cycle</h3>
              <p>This query-only harness exercises the all-data ONNX artifact on a bundled pair for physical-device timing. The pair was part of training, so its numeric output is deliberately suppressed and is not evaluation evidence.</p>
              <ModelStatus state={modelState} />
              <div
                className="asset-status"
                data-testid="fixed-example-ready"
                data-sample-id={selected.id}
                data-before-sha256={assetState.status === "ready" ? assetState.assets.before.sha256 : undefined}
                data-after-sha256={assetState.status === "ready" ? assetState.assets.after.sha256 : undefined}
                role={assetState.status === "error" ? "alert" : "status"}
                aria-live={assetState.status === "error" ? "assertive" : "polite"}
              >
                {assetState.status === "loading" ? "Preparing the bundled pair…" : null}
                {assetState.status === "ready" ? `Bundled pair ${assetState.sampleId} ready.` : null}
                {assetState.status === "error" ? `Bundled pair unavailable: ${assetState.message}` : null}
              </div>
            </div>
            <div className="replay-action">
              <button type="button" className="replay-button" onClick={() => void runFixedReplay()} disabled={!replayReady || replay.status === "running"} data-testid="run-fixed-example" data-sample-id={selected.id}>
                {replay.status === "running" ? "Running fixed replay…" : <>Run fixed replay <ArrowIcon /></>}
              </button>
              {replay.status === "complete" ? (
                <div
                  className="replay-output"
                  data-testid="runtime-output"
                  data-sample-id={replay.binding.sampleId}
                  data-replay-id={replay.binding.replayId}
                  data-processing-ms={replay.processingMs.toFixed(6)}
                  data-model-version={replay.modelVersion}
                  data-test-adapter={replay.isTestAdapter ? "true" : "false"}
                  role="status"
                >
                  <span>{replay.isTestAdapter ? "Synthetic test cycle" : "Fixed worker cycle complete"}</span>
                  <strong>{Math.round(replay.processingMs)} ms</strong>
                  <small>{replay.modelVersion}</small>
                  <p>No numeric model output is rendered. This timing harness is not evaluation evidence.</p>
                </div>
              ) : null}
              {replay.status === "error" ? <div className="inline-alert" role="alert">{replay.message}</div> : null}
            </div>
          </section> : null}
        </section>

        <section className="method-section" id="method" aria-labelledby="method-title">
          <div className="section-heading light">
            <div><p className="eyebrow">What the experiment tested</p><h2 id="method-title">A frozen, category-disjoint comparison.</h2></div>
            <p>Every valid pair appeared in one untouched outer fold; food category never entered the model.</p>
          </div>
          <ol className="method-grid">
            <li><span>01</span><h3>Pair</h3><p>A shared MobileNet encoder processed standardized before and after images.</p></li>
            <li><span>02</span><h3>Hold out categories</h3><p>Five duplicate-safe folds tested transfer to categories absent from training.</p></li>
            <li><span>03</span><h3>Compare honestly</h3><p>The paired model beat non-neural baselines, but lost to the after-only ablation.</p></li>
          </ol>
        </section>

        <section className="limits-section" id="limits" aria-labelledby="limits-title">
          <div className="limits-copy">
            <p className="eyebrow">Release boundaries</p><h2 id="limits-title">What this benchmark cannot establish.</h2>
            <p>Evidence comes from one controlled Indonesian hospital acquisition setup. It does not establish validity for arbitrary meals, new cameras, UAE settings, or operations.</p>
          </div>
          <div className="limits-list">
            <article><span>01</span><div><h3>No custom-image estimate</h3><p>The numeric-demo gate failed, so the public interface accepts no uploads and makes no new-image claim.</p></div></article>
            <article><span>02</span><div><h3>No public uncertainty interval</h3><p>Coverage was adequate in aggregate, but mean interval width exceeded the frozen gate.</p></div></article>
            <article><span>03</span><div><h3>No useful-abstention claim</h3><p>Error fell among retained cases, but retention was too low and badly uneven across target slices.</p></div></article>
            <article><span>04</span><div><h3>No waste-reduction claim</h3><p>This study measured benchmark error. It did not test behavior, savings, or institutional impact.</p></div></article>
            <article><span>05</span><div><h3>Possible source-label tensions</h3><p>Several AI-assisted post-hoc visual reviews found records that appear to conflict with recorded mass. These are hypotheses, not causal findings or declared label errors; the records remain in the frozen evaluation.</p></div></article>
          </div>
        </section>

        <section className="attribution-section" aria-labelledby="attribution-title">
          <div><p className="eyebrow">Data and model attribution</p><h2 id="attribution-title">LeFood-Set v1 · CC BY 4.0</h2></div>
          <p>Example images and the dataset-derived model: Yuita Arum Sari, Yudi Arimba Wani, and Atsushi Nakazawa, LeFood-Set v1, DOI 10.17632/cchsk79jkt.1. Image files are unmodified and renamed only by source ID and role. Five close predictions and five largest errors are shown; this is not a random sample.</p>
          <div className="attribution-links">
            <a href="https://doi.org/10.17632/cchsk79jkt.1" rel="noreferrer">Dataset record <ArrowIcon /></a>
            <a href={`${import.meta.env.BASE_URL}legal/NOTICE.txt`}>Release notices <ArrowIcon /></a>
          </div>
        </section>
      </main>

      <footer>
        <div className="brand footer-brand"><span className="brand-mark" aria-hidden="true"><span /></span><span>PlateGauge</span></div>
        <div className="footer-disclosure">
          <p>Substantially AI-assisted. Taysir Al Daqrouq set the objectives and constraints, approved the protocol and claim boundaries, and reviewed the frozen evidence.</p>
          <p>This explorer accepts no uploads and sends no inference API requests. GitHub Pages serves the static files and may process ordinary request metadata.</p>
        </div>
        <div className="footer-links">
          <a href={`${import.meta.env.BASE_URL}legal/PRIVACY_NOTICE.md`}>Privacy</a>
          <a href={`${import.meta.env.BASE_URL}legal/NOTICE.txt`}>Notices</a>
          <a href={`${import.meta.env.BASE_URL}legal/THIRD_PARTY_LICENSES.json`}>Dependency licenses</a>
          <a href={`${import.meta.env.BASE_URL}legal/AI_ASSISTANCE_LOG.md`}>AI-assistance disclosure</a>
          {sourceUrl ? <a href={sourceUrl} rel="noreferrer">Source</a> : <span>Source unavailable in this development build</span>}
        </div>
      </footer>
    </>
  );
}
