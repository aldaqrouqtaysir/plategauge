"""Versioned manifest schema and deterministic CSV serialization."""

from __future__ import annotations

import csv
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import DataIntegrityError
from .folds import fold_for_category

MANIFEST_SCHEMA_VERSION = "1.0"
DATASET_DOI = "10.17632/cchsk79jkt.1"
DATASET_VERSION = "LeFood-Set v1"
DATASET_LICENSE = "CC BY 4.0"

_CATEGORY_PATTERN = re.compile(r"^\d{3}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MANIFEST_FIELDS = (
    "schema_version",
    "sample_id",
    "source_row",
    "food_name",
    "category",
    "before_path",
    "after_path",
    "before_mass_g",
    "after_mass_g",
    "leftover_fraction",
    "observer_score",
    "before_width",
    "before_height",
    "after_width",
    "after_height",
    "before_sha256",
    "after_sha256",
    "duplicate_group",
    "is_valid",
    "exclusion_reason",
    "outer_fold",
    "source_doi",
    "dataset_version",
    "license",
)


@dataclass(frozen=True, slots=True)
class ManifestRecord:
    """One matched before/after pair, including excluded matched pairs."""

    sample_id: str
    source_row: int
    food_name: str
    category: str
    before_path: str
    after_path: str
    before_mass_g: float
    after_mass_g: float
    leftover_fraction: float
    observer_score: int
    before_width: int
    before_height: int
    after_width: int
    after_height: int
    before_sha256: str
    after_sha256: str
    duplicate_group: str = ""
    is_valid: bool = True
    exclusion_reason: str = ""
    outer_fold: int = -1
    source_doi: str = DATASET_DOI
    dataset_version: str = DATASET_VERSION
    license: str = DATASET_LICENSE
    schema_version: str = MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MANIFEST_SCHEMA_VERSION:
            raise DataIntegrityError(f"Unsupported manifest schema {self.schema_version!r}")
        if not self.sample_id.strip():
            raise DataIntegrityError("sample_id must be non-empty")
        if self.source_row < 2:
            raise DataIntegrityError("source_row must reference a data row in the workbook")
        if not _CATEGORY_PATTERN.fullmatch(self.category):
            raise DataIntegrityError(f"Invalid category code {self.category!r}")
        for label, value in (
            ("before_mass_g", self.before_mass_g),
            ("after_mass_g", self.after_mass_g),
            ("leftover_fraction", self.leftover_fraction),
        ):
            if not math.isfinite(value):
                raise DataIntegrityError(f"{label} must be finite")
        if self.before_mass_g <= 0 or self.after_mass_g < 0:
            raise DataIntegrityError("Masses require before > 0 and after >= 0")
        expected_target = self.after_mass_g / self.before_mass_g
        if not math.isclose(self.leftover_fraction, expected_target, rel_tol=0.0, abs_tol=1e-12):
            raise DataIntegrityError("leftover_fraction must equal after_mass_g / before_mass_g")
        if self.is_valid and not 0.0 <= self.leftover_fraction <= 1.0:
            raise DataIntegrityError("Valid targets must lie in [0, 1]")
        if self.is_valid and self.exclusion_reason:
            raise DataIntegrityError("Valid records cannot have an exclusion reason")
        if not self.is_valid and not self.exclusion_reason:
            raise DataIntegrityError("Excluded records require an exclusion reason")
        if not 1 <= self.observer_score <= 7:
            raise DataIntegrityError("observer_score must be in [1, 7]")
        if min(self.before_width, self.before_height, self.after_width, self.after_height) <= 0:
            raise DataIntegrityError("Image dimensions must be positive")
        for label, digest in (("before_sha256", self.before_sha256), ("after_sha256", self.after_sha256)):
            if not _SHA256_PATTERN.fullmatch(digest):
                raise DataIntegrityError(f"{label} is not a lowercase SHA-256 digest")
        if self.outer_fold != fold_for_category(self.category):
            raise DataIntegrityError(
                f"outer_fold {self.outer_fold} does not match frozen category assignment"
            )
        for label, path in (("before_path", self.before_path), ("after_path", self.after_path)):
            candidate = Path(path)
            if candidate.is_absolute() or ".." in candidate.parts:
                raise DataIntegrityError(f"{label} must be a safe dataset-relative path")

    def to_row(self) -> dict[str, str]:
        """Serialize without locale-sensitive formatting."""

        raw = asdict(self)
        row: dict[str, str] = {}
        for key in MANIFEST_FIELDS:
            value = raw[key]
            if isinstance(value, bool):
                row[key] = "true" if value else "false"
            elif isinstance(value, float):
                row[key] = format(value, ".17g")
            else:
                row[key] = str(value)
        return row

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ManifestRecord:
        """Parse a row from CSV, rejecting ambiguous booleans."""

        valid_token = str(row["is_valid"]).strip().lower()
        if valid_token not in {"true", "false"}:
            raise DataIntegrityError("is_valid must be 'true' or 'false'")
        return cls(
            schema_version=str(row["schema_version"]),
            sample_id=str(row["sample_id"]),
            source_row=int(row["source_row"]),
            food_name=str(row["food_name"]),
            category=str(row["category"]),
            before_path=str(row["before_path"]),
            after_path=str(row["after_path"]),
            before_mass_g=float(row["before_mass_g"]),
            after_mass_g=float(row["after_mass_g"]),
            leftover_fraction=float(row["leftover_fraction"]),
            observer_score=int(row["observer_score"]),
            before_width=int(row["before_width"]),
            before_height=int(row["before_height"]),
            after_width=int(row["after_width"]),
            after_height=int(row["after_height"]),
            before_sha256=str(row["before_sha256"]),
            after_sha256=str(row["after_sha256"]),
            duplicate_group=str(row.get("duplicate_group", "")),
            is_valid=valid_token == "true",
            exclusion_reason=str(row.get("exclusion_reason", "")),
            outer_fold=int(row["outer_fold"]),
            source_doi=str(row["source_doi"]),
            dataset_version=str(row["dataset_version"]),
            license=str(row["license"]),
        )


def read_manifest(path: str | Path) -> list[ManifestRecord]:
    """Read and validate a manifest CSV."""

    manifest_path = Path(path)
    with manifest_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
            raise DataIntegrityError(
                f"Manifest columns differ from schema: {tuple(reader.fieldnames or ())!r}"
            )
        records = [ManifestRecord.from_row(row) for row in reader]
    sample_ids = [record.sample_id for record in records]
    if len(sample_ids) != len(set(sample_ids)):
        raise DataIntegrityError("sample_id values must be unique")
    return records


def write_manifest(records: list[ManifestRecord], path: str | Path) -> None:
    """Write a deterministically ordered manifest CSV."""

    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(records, key=lambda record: (record.source_row, record.sample_id))
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(record.to_row() for record in ordered)
