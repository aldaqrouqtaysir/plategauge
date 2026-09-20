# PlateGauge release assets

Production builds intentionally contain no placeholder prediction model. A frozen release must provide:

- `plategauge.onnx`
- `release.json`

The release manifest is validated before inference and must have this shape:

```json
{
  "schemaVersion": 1,
  "modelVersion": "v1.0.0",
  "modelPath": "models/plategauge.onnx",
  "modelSha256": "64 lowercase hexadecimal characters",
  "beforeInputName": "before",
  "afterInputName": "after",
  "outputName": "quantiles",
  "calibration": {
    "lowerExpansion": 0,
    "upperExpansion": 0,
    "abstentionWidth": 0.3,
    "intervalGatePassed": false
  }
}
```

The ONNX artifact and any included LeFood-derived example images require CC BY 4.0 attribution and change notices.
