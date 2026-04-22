"""Tests for the wheel-first edge artifact builder."""

import json

from seavision.edge.bundle import ArtifactBuilder
from seavision.edge.config import ARTIFACT_MANIFEST_FILENAME, ArtifactManifest, EdgeConfig


class TestArtifactBuilder:
    """Test artifact creation for the edge runtime."""

    def test_build_creates_artifact_files(self, tmp_path):
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake onnx model data")

        meta_path = tmp_path / "model.json"
        meta_path.write_text(json.dumps({
            "imgsz": 320,
            "num_classes": 2,
            "class_names": {"0": "fish", "1": "seal"},
        }))

        artifact_dir = tmp_path / "artifact"
        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
            edge_config=EdgeConfig(conf_threshold=0.5),
        )

        builder.build()

        assert (artifact_dir / "model.onnx").exists()
        assert (artifact_dir / "config.json").exists()
        assert (artifact_dir / "export_metadata.json").exists()
        assert (artifact_dir / ARTIFACT_MANIFEST_FILENAME).exists()

        manifest = ArtifactManifest.from_file(
            artifact_dir / ARTIFACT_MANIFEST_FILENAME
        )
        assert manifest.model.path == "model.onnx"
        assert manifest.runtime_config.path == "config.json"
        assert manifest.export_metadata.path == "export_metadata.json"

    def test_build_config_inherits_export_metadata(self, tmp_path):
        model_path = tmp_path / "model.onnx"
        model_path.write_bytes(b"fake onnx model data")

        meta_path = tmp_path / "model.json"
        meta_path.write_text(json.dumps({
            "imgsz": 320,
            "num_classes": 3,
            "class_names": {"0": "fish", "1": "seal", "2": "debris"},
        }))

        artifact_dir = tmp_path / "artifact"
        builder = ArtifactBuilder(
            exported_model_path=str(model_path),
            export_metadata_path=str(meta_path),
            output_dir=str(artifact_dir),
            edge_config=EdgeConfig(conf_threshold=0.5, frame_skip=3),
        )

        builder.build()

        config = EdgeConfig.from_file(str(artifact_dir / "config.json"))
        assert config.imgsz == 320
        assert config.num_classes == 3
        assert config.class_names == {0: "fish", 1: "seal", 2: "debris"}
        assert config.conf_threshold == 0.5
        assert config.frame_skip == 3