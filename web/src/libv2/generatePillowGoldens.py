"""Generate synthetic-only resize references with installed Pillow; never overwrite."""

import hashlib
import json
import argparse
from pathlib import Path

import numpy as np
import PIL
from PIL import Image


def source(width, height, kind):
    y, x = np.indices((height, width), dtype=np.int64)
    data = np.empty((height, width, 3), dtype=np.uint8)
    if kind == "pattern":
        data[..., 0] = (x * 17 + y * 11) % 256
        data[..., 1] = (x + y) % 2 * 255
        data[..., 2] = ((x * 7 + y * 13) % 31 < 15) * 255
    elif kind == "edges":
        data[..., 0] = (x < width // 2) * 255
        data[..., 1] = (y < height // 2) * 255
        data[..., 2] = ((x == 0) | (y == height - 1)) * 255
    elif kind == "uniform":
        data[:] = (17, 101, 233)
    else:
        raise ValueError(kind)
    return Image.fromarray(data)


fixtures = []
for mode, shapes in (
    ("resize", [(1, 1, 13, 7), (1, 17, 23, 7), (17, 1, 7, 23), (2, 3, 17, 19),
                (17, 19, 2, 3), (13, 13, 13, 13), (13, 17, 13, 9), (13, 17, 21, 17),
                (64, 41, 29, 17), (41, 64, 17, 29), (641, 479, 343, 256),
                (513, 513, 256, 256), (100, 80, 320, 256), (511, 257, 256, 129),
                (1024, 768, 1, 1), (1, 257, 1, 129), (257, 1, 129, 1), (16, 17, 257, 1),
                (5, 499, 7, 127), (5, 500, 7, 127), (5, 501, 7, 127),
                (5, 1023, 7, 127), (5, 501, 7, 600)]),
    ("crop", [(256, 256), (641, 479), (479, 641), (513, 513), (100, 80),
              (80, 100), (513, 512), (515, 512)]),
):
    for shape in shapes:
        for kind in ("pattern", "edges", "uniform"):
            width, height = shape[:2]
            image = source(width, height, kind)
            if mode == "resize":
                output_width, output_height = shape[2:]
                expected = image.resize((output_width, output_height), Image.Resampling.BICUBIC)
            else:
                scale = 256 / min(width, height)
                resized = (max(256, round(width * scale)), max(256, round(height * scale)))
                expected = image.resize(resized, Image.Resampling.BICUBIC)
                left, top = (resized[0] - 224) // 2, (resized[1] - 224) // 2
                expected = expected.crop((left, top, left + 224, top + 224))
                output_width = output_height = 224
            rgba = expected.convert("RGBA").tobytes()
            fixtures.append({"id": f"{mode}-{width}x{height}-{output_width}x{output_height}-{kind}",
                             "mode": mode, "width": width, "height": height,
                             "outputWidth": output_width, "outputHeight": output_height,
                             "kind": kind, "expectedRgbaSha256": hashlib.sha256(rgba).hexdigest()})

payload = {"syntheticOnly": True, "pillowVersion": PIL.__version__,
           "generatorSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           "comparison": "exact SHA-256 of all output RGBA bytes; no tolerance",
           "fixtures": fixtures}
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, default=Path(__file__).with_name("pillowResizeGoldens.json"))
destination = parser.parse_args().output
with destination.open("x", encoding="utf-8", newline="\n") as output:
    json.dump(payload, output, indent=2)
    output.write("\n")
print(f"Generated {len(fixtures)} synthetic Pillow {PIL.__version__} golden hashes.")
