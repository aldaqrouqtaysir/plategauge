"""Collect a real local PlateGauge browser benchmark on a physical laptop."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from plategauge.browser_measurement import collect_browser_measurement
from plategauge.errors import PlateGaugeError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-physical-device", action="store_true")
    parser.add_argument("--device-label", default="PlateGauge reference laptop")
    parser.add_argument(
        "--release-evidence",
        type=Path,
        default=Path("artifacts/plategauge.onnx.evidence.json"),
    )
    parser.add_argument("--results", type=Path, default=Path("reports/results.json"))
    parser.add_argument("--web-root", type=Path, default=Path("web/dist"))
    parser.add_argument(
        "--observer-script",
        type=Path,
        default=Path("web/scripts/collect-browser-observation.mjs"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release/browser-benchmark-measurement.json"),
    )
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--measurements", type=int, default=20)
    parser.add_argument(
        "--browser-channel", choices=("chrome", "msedge", "chromium"), default="chrome"
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--base-path", default="/plategauge/")
    parser.add_argument("--node-binary", default="node")
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    arguments = parser.parse_args(argv)
    try:
        measurement = collect_browser_measurement(
            evidence_path=arguments.release_evidence,
            results_path=arguments.results,
            web_root=arguments.web_root,
            observer_script=arguments.observer_script,
            output_path=arguments.output,
            device_label=arguments.device_label,
            physical_device_confirmed=arguments.confirm_physical_device,
            warmups=arguments.warmups,
            measurements=arguments.measurements,
            browser_channel=arguments.browser_channel,
            headless=arguments.headless,
            base_path=arguments.base_path,
            node_binary=arguments.node_binary,
            timeout_seconds=arguments.timeout_seconds,
        )
    except (PlateGaugeError, OSError, ValueError) as exc:
        print(
            json.dumps({"status": "blocked", "error": type(exc).__name__, "message": str(exc)}),
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {
                "status": "measured",
                "output": str(arguments.output),
                "browser": measurement["runtime"]["browser_name"],
                "browser_mode": measurement["runtime"]["browser_mode"],
                "fixed_sample_id": measurement["benchmark_input"]["sample_id"],
                "numeric_prediction_recorded": measurement["benchmark_input"][
                    "numeric_prediction_recorded"
                ],
                "warm_measurements": len(measurement["measurements"]["warm_inference_ms"]),
                "memory_method": measurement["measurements"]["memory_measurement_method"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
