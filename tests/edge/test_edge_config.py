"""Tests for the edge configuration module."""

import json
import pytest
from pathlib import Path

from seavision.edge.config import (
    ARTIFACT_MANIFEST_FILENAME,
    ArtifactManifest,
    EdgeConfig,
)


class TestEdgeConfig:
    """Test EdgeConfig defaults, serialisation, and loading."""

    def test_defaults(self):
        config = EdgeConfig()
        assert config.model_path == "model.onnx"
        assert config.imgsz == 640
        assert config.conf_threshold == 0.25
        assert config.iou_threshold == 0.45
        assert config.frame_skip == 1
        assert config.ort_threads == 0

    def test_round_trip_json(self, tmp_path):
        """Config should survive save → load without data loss."""
        config = EdgeConfig(
            model_path="custom_model.onnx",
            imgsz=320,
            conf_threshold=0.4,
            num_classes=3,
            class_names={0: "fish", 1: "seal", 2: "debris"},
            frame_skip=5,
        )

        config_file = str(tmp_path / "config.json")
        config.to_file(config_file)

        loaded = EdgeConfig.from_file(config_file)

        assert loaded.model_path == "custom_model.onnx"
        assert loaded.imgsz == 320
        assert loaded.conf_threshold == 0.4
        assert loaded.num_classes == 3
        assert loaded.class_names == {0: "fish", 1: "seal", 2: "debris"}
        assert loaded.frame_skip == 5

    def test_class_names_keys_are_int_after_load(self, tmp_path):
        """JSON converts int keys to strings; from_file must convert back."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "model_path": "m.onnx",
            "class_names": {"0": "fish", "1": "seal"},
        }))

        loaded = EdgeConfig.from_file(str(config_file))
        assert all(isinstance(k, int) for k in loaded.class_names.keys())

    def test_from_file_missing_raises(self):
        with pytest.raises(FileNotFoundError):
            EdgeConfig.from_file("/nonexistent/config.json")

    def test_ignores_unknown_fields(self, tmp_path):
        """Future config fields should not crash older loaders."""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "model_path": "m.onnx",
            "future_field": "unknown_value",
        }))

        loaded = EdgeConfig.from_file(str(config_file))
        assert loaded.model_path == "m.onnx"

    def test_artifact_manifest_round_trip_json(self, tmp_path):
        manifest = ArtifactManifest(
            artifact_version="1.2.3",
            runtime_version_range=">=1.0.0,<2.0.0",
        )

        manifest_path = tmp_path / ARTIFACT_MANIFEST_FILENAME
        manifest.to_file(manifest_path)

        loaded = ArtifactManifest.from_file(manifest_path)
        assert loaded.artifact_version == "1.2.3"
        assert loaded.runtime_version_range == ">=1.0.0,<2.0.0"
        assert loaded.model.path == "model.onnx"
        assert loaded.runtime_config.path == "config.json"

    def test_from_artifact_dir_loads_runtime_config_and_model_path(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({
            "model_path": "ignored-by-artifact-loader.onnx",
            "imgsz": 320,
            "class_names": {"0": "fish"},
        }))

        manifest = ArtifactManifest()
        manifest.to_file(tmp_path / ARTIFACT_MANIFEST_FILENAME)

        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"fake model")
        (tmp_path / "export_metadata.json").write_text("{}")

        loaded = EdgeConfig.from_artifact_dir(tmp_path)

        assert loaded.imgsz == 320
        assert loaded.class_names == {0: "fish"}
        assert Path(loaded.model_path) == model_file

    def test_from_artifact_dir_missing_manifest_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            EdgeConfig.from_artifact_dir(tmp_path)