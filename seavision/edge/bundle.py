"""Artifact builder for wheel-first edge deployment.

Creates an artifact directory containing the exported model, runtime config,
export metadata, and a manifest with compatibility and integrity information.
The SeaVision wheel is installed separately on the edge device.
"""

import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from seavision import __version__

from .config import (
    ARTIFACT_MANIFEST_FILENAME,
    ArtifactFile,
    ArtifactManifest,
    EdgeConfig,
)

logger = logging.getLogger(__name__)


class ArtifactBuilder:
    """
    Package an exported model into a deployable edge artifact directory.

    The resulting directory is copied to the edge device separately from the
    SeaVision wheel. The runtime then loads the artifact via
    ``seavision-edge --artifact-dir <path>``.
    """

    def __init__(
        self,
        exported_model_path: str,
        export_metadata_path: str,
        output_dir: str = "./artifact",
        edge_config: Optional[EdgeConfig] = None,
    ):
        """
        Initialise the builder.

        Args:
            exported_model_path: Path to the exported model file (e.g.
                model.onnx).
            export_metadata_path: Path to the export_metadata.json file
                written by ModelExporter.
            output_dir: Directory to create the artifact in.
            edge_config: Optional pre-configured EdgeConfig. If None,
                defaults are populated from the export metadata.
        """
        self.exported_model_path = Path(exported_model_path)
        self.export_metadata_path = Path(export_metadata_path)
        self.output_dir = Path(output_dir)
        self.edge_config = edge_config

    def build(self) -> str:
        """
        Build the deployment artifact.

        Returns:
            Path to the artifact directory.

        Raises:
            FileNotFoundError: If the model or metadata file is missing.
        """
        if not self.exported_model_path.exists():
            raise FileNotFoundError(
                f"Exported model not found: {self.exported_model_path}"
            )
        if not self.export_metadata_path.exists():
            raise FileNotFoundError(
                f"Export metadata not found: {self.export_metadata_path}"
            )

        # Load export metadata
        with open(self.export_metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        artifact_dir = self.output_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)

        # --- 1. Copy model ---
        model_dest = artifact_dir / self.exported_model_path.name
        if self.exported_model_path.is_dir():
            if model_dest.exists():
                shutil.rmtree(model_dest)
            shutil.copytree(self.exported_model_path, model_dest)
        else:
            shutil.copy2(self.exported_model_path, model_dest)
        logger.info("Copied model to artifact: %s", model_dest.name)

        # --- 2. Copy metadata ---
        shutil.copy2(
            self.export_metadata_path, artifact_dir / "export_metadata.json"
        )

        # --- 3. Build and write EdgeConfig ---
        config = self._build_edge_config(metadata, model_dest.name)
        config_path = artifact_dir / "config.json"
        config.to_file(str(config_path))

        # --- 4. Write artifact manifest ---
        manifest = self._build_manifest(
            artifact_version=__version__,
            model_path=model_dest,
            config_path=config_path,
            metadata_path=artifact_dir / "export_metadata.json",
        )
        manifest.to_file(artifact_dir / ARTIFACT_MANIFEST_FILENAME)

        logger.info("Artifact created: %s", artifact_dir)
        return str(artifact_dir)

    def _build_edge_config(
        self,
        metadata: dict,
        model_filename: str,
    ) -> EdgeConfig:
        """
        Build an EdgeConfig from export metadata, overriding with any
        user-provided config values.
        """
        # Start from user config or defaults
        config = self.edge_config or EdgeConfig()

        # Override with export metadata (these must match the export)
        config.model_path = model_filename
        config.imgsz = metadata.get("imgsz", config.imgsz)
        config.num_classes = metadata.get("num_classes", config.num_classes)

        class_names_raw = metadata.get("class_names", {})
        config.class_names = {int(k): v for k, v in class_names_raw.items()}

        return config
    
    def _build_manifest(
        self,
        artifact_version: str,
        model_path: Path,
        config_path: Path,
        metadata_path: Path,
    ) -> ArtifactManifest:
        """Build the artifact manifest for runtime loading and validation."""
        return ArtifactManifest(
            artifact_version=artifact_version,
            runtime_version_range=self._default_runtime_version_range(),
            model=ArtifactFile(
                path=model_path.name,
                sha256=self._sha256_for_path(model_path),
            ),
            runtime_config=ArtifactFile(
                path=config_path.name,
                sha256=self._sha256_for_path(config_path),
            ),
            export_metadata=ArtifactFile(
                path=metadata_path.name,
                sha256=self._sha256_for_path(metadata_path),
            ),
        )

    @staticmethod
    def _default_runtime_version_range() -> str:
        import re

        match = re.match(r"^(\d+)\.(\d+)\.(\d+)", __version__)
        if not match:
            raise ValueError(f"Unsupported SeaVision version format: {__version__}")

        major = int(match.group(1))
        minor = int(match.group(2))
        return f">={__version__},<{major}.{minor + 1}.0"

    @staticmethod
    def _sha256_for_path(path: Path) -> str:
        if path.is_dir():
            return ""

        digest = hashlib.sha256()
        with open(path, "rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(8192), b""):
                digest.update(chunk)
        return digest.hexdigest()


BundleBuilder = ArtifactBuilder