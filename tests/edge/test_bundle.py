"""Tests for the edge artifact builder."""

import json
import pytest

from seavision.edge.bundle import ArtifactBuilder
from seavision.edge.config import (
    ARTIFACT_MANIFEST_FILENAME,
    ArtifactManifest,
    EdgeConfig,
)
from seavision import __version__


class TestArtifactBuilder:
    """Test artifact creation."""

    @pytest.fixture
    def mock_export(self, tmp_path):
        """Create a fake exported model and metadata."""
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake onnx model data")

        metadata = {
            "seavision_export_version": 1,
            "source_weights": "fish.pt",
            "target": "ONNX",
            "imgsz": 320,
            "half": False,
            "int8": False,
            "num_classes": 3,
            "class_names": {"0": "fish", "1": "seal", "2": "debris"},
        }
        meta_path = tmp_path / "model.json"
        meta_path.write_text(json.dumps(metadata))

        return model_path, meta_path

    def test_build_creates_all_files(self, tmp_path, mock_export):
        model_path, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
        )
        result = builder.build()

        assert result == str(artifact_dir)
        assert (artifact_dir / "model.onnx").exists()
        assert (artifact_dir / "config.json").exists()
        assert (artifact_dir / "export_metadata.json").exists()
        assert (artifact_dir / ARTIFACT_MANIFEST_FILENAME).exists()

    def test_manifest_contains_integrity_entries(self, tmp_path, mock_export):
        """The manifest should track required runtime files and checksums."""
        model_path, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
        )
        builder.build()

        manifest = ArtifactManifest.from_file(
            artifact_dir / ARTIFACT_MANIFEST_FILENAME
        )
        assert manifest.model.path == "model.onnx"
        assert manifest.runtime_config.path == "config.json"
        assert manifest.export_metadata.path == "export_metadata.json"
        assert manifest.model.sha256
        assert manifest.runtime_config.sha256
        assert manifest.export_metadata.sha256

    def test_config_inherits_export_metadata(self, tmp_path, mock_export):
        model_path, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
        )
        builder.build()

        config = EdgeConfig.from_file(str(artifact_dir / "config.json"))
        assert config.imgsz == 320
        assert config.num_classes == 3
        assert config.class_names == {0: "fish", 1: "seal", 2: "debris"}

    def test_manifest_sets_runtime_compatibility_range(self, tmp_path, mock_export):
        model_path, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
        )
        builder.build()

        manifest = ArtifactManifest.from_file(
            artifact_dir / ARTIFACT_MANIFEST_FILENAME
        )
        assert manifest.runtime_version_range.startswith(f">={__version__}")

    def test_edge_config_overrides_apply(self, tmp_path, mock_export):
        model_path, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        edge_config = EdgeConfig(conf_threshold=0.5, frame_skip=3)
        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
            edge_config=edge_config,
        )
        builder.build()

        config = EdgeConfig.from_file(str(artifact_dir / "config.json"))
        assert config.conf_threshold == 0.5
        assert config.frame_skip == 3
        # But metadata-derived fields still set correctly
        assert config.imgsz == 320

    def test_missing_model_raises(self, tmp_path, mock_export):
        _, meta_path = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path="/nonexistent/model.onnx",
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
        )
        with pytest.raises(FileNotFoundError):
            builder.build()

    def test_missing_metadata_raises(self, tmp_path, mock_export):
        model_path, _ = mock_export
        artifact_dir = tmp_path / "artifact"

        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path="/nonexistent/meta.json",
            output_dir=str(artifact_dir),
        )
        with pytest.raises(FileNotFoundError):
            builder.build()