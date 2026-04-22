"""Tests for the model export module."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from seavision.engine.export.config import (
    ExportConfig,
    ExportResult,
    ExportTarget,
    TARGET_EXPORT_INFO,
    ValidationResult,
)
from seavision.engine.export.exporter import ModelExporter


class TestExportConfig:
    """Test ExportConfig defaults and target mapping."""

    def test_default_target_is_onnx(self):
        config = ExportConfig()
        assert config.target == ExportTarget.ONNX

    def test_default_imgsz_is_640(self):
        config = ExportConfig()
        assert config.imgsz == 640

    def test_all_targets_have_export_info(self):
        for target in ExportTarget:
            assert target in TARGET_EXPORT_INFO
            info = TARGET_EXPORT_INFO[target]
            assert "format" in info
            assert "suffix" in info
            assert "runtime_package" in info

    def test_onnx_target_info(self):
        info = TARGET_EXPORT_INFO[ExportTarget.ONNX]
        assert info["format"] == "onnx"
        assert info["suffix"] == ".onnx"
        assert info["runtime_package"] == "onnxruntime"


class TestExportResult:
    """Test ExportResult construction."""

    def test_default_is_failure(self):
        result = ExportResult()
        assert result.success is False
        assert result.exported_path == ""

    def test_success_result(self):
        result = ExportResult(
            success=True,
            exported_path="/tmp/model.onnx",
            model_size_mb=5.2,
            num_classes=3,
            class_names={0: "fish", 1: "seal", 2: "debris"},
        )
        assert result.success is True
        assert result.num_classes == 3
        assert result.class_names[1] == "seal"


class TestValidationResult:
    """Test ValidationResult construction."""

    def test_default_is_failure(self):
        result = ValidationResult()
        assert result.passed is False

    def test_passed_result(self):
        result = ValidationResult(
            passed=True,
            num_detections_pytorch=5,
            num_detections_exported=5,
            max_box_deviation=0.3,
            max_confidence_deviation=0.001,
            details="All checks passed",
        )
        assert result.passed is True
        assert result.max_box_deviation < 5.0


class TestModelExporter:
    """Test the model exporter."""

    def test_missing_weights_returns_failure(self):
        config = ExportConfig(weights_path="/nonexistent/model.pt")
        exporter = ModelExporter(config)
        result = exporter.export()
        assert result.success is False
        assert "not found" in result.error

    def test_missing_ultralytics_returns_failure(self, tmp_path):
        """If ultralytics is not importable, export should fail gracefully."""
        weights = tmp_path / "model.pt"
        weights.write_bytes(b"fake weights data")
        config = ExportConfig(weights_path=str(weights))
        exporter = ModelExporter(config)

        with patch.dict("sys.modules", {"ultralytics": None}):
            with patch(
                "seavision.engine.export.exporter.ModelExporter.export"
            ) as mock_export:
                # Simulate the ImportError path
                mock_export.return_value = ExportResult(
                    success=False,
                    config=config,
                    error="Ultralytics is required for model export.",
                )
                result = mock_export()
                assert result.success is False
                assert "Ultralytics" in result.error