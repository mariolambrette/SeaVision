"""Tests for the edge runtime CLI entrypoint."""

import sys
from pathlib import Path

from seavision.edge.config import ARTIFACT_MANIFEST_FILENAME, EdgeConfig
from seavision.run_edge import main


class TestRunEdgeCli:
    """Test artifact-based edge CLI startup behaviour."""

    def test_main_loads_artifact_dir_and_applies_overrides(self, monkeypatch):
        loaded_paths = []
        config = EdgeConfig()
        runtime_configs = []

        def fake_from_artifact_dir(path):
            loaded_paths.append(path)
            return config

        class FakeRuntime:
            def __init__(self, runtime_config):
                runtime_configs.append(runtime_config)

            def run(self):
                runtime_configs.append("ran")

        monkeypatch.setattr(
            "seavision.edge.config.EdgeConfig.from_artifact_dir",
            fake_from_artifact_dir,
        )
        monkeypatch.setattr("seavision.run_edge._load_runtime_class", lambda: FakeRuntime)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "seavision-edge",
                "--artifact-dir",
                "./artifact",
                "--source",
                "video.mp4",
                "--conf",
                "0.4",
                "--frame-skip",
                "5",
            ],
        )

        exit_code = main()

        assert exit_code == 0
        assert loaded_paths == ["./artifact"]
        assert runtime_configs[0].source == "video.mp4"
        assert runtime_configs[0].conf_threshold == 0.4
        assert runtime_configs[0].frame_skip == 5
        assert runtime_configs[1] == "ran"

    def test_main_returns_error_for_missing_artifact(self, monkeypatch, capsys):
        def fake_from_artifact_dir(path):
            raise FileNotFoundError(path)

        monkeypatch.setattr(
            "seavision.edge.config.EdgeConfig.from_artifact_dir",
            fake_from_artifact_dir,
        )
        monkeypatch.setattr("seavision.run_edge._load_runtime_class", lambda: None)
        monkeypatch.setattr(
            sys,
            "argv",
            ["seavision-edge", "--artifact-dir", "./missing-artifact"],
        )

        exit_code = main()
        captured = capsys.readouterr()

        assert exit_code == 1
        assert "./missing-artifact" in captured.out
        assert "edge artifact directory" in captured.out

    def test_main_auto_selects_nested_artifact_dir(self, monkeypatch, tmp_path):
        parent_dir = tmp_path / "wheel_test_1"
        nested_artifact_dir = parent_dir / "artifact"
        nested_artifact_dir.mkdir(parents=True)
        (nested_artifact_dir / ARTIFACT_MANIFEST_FILENAME).write_text("{}")

        loaded_paths = []
        config = EdgeConfig()

        def fake_from_artifact_dir(path):
            loaded_paths.append(path)
            return config

        class FakeRuntime:
            def __init__(self, runtime_config):
                self.runtime_config = runtime_config

            def run(self):
                return None

        monkeypatch.setattr(
            "seavision.edge.config.EdgeConfig.from_artifact_dir",
            fake_from_artifact_dir,
        )
        monkeypatch.setattr(
            "seavision.run_edge._load_runtime_class", lambda: FakeRuntime
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["seavision-edge", "--artifact-dir", str(parent_dir)],
        )

        exit_code = main()

        assert exit_code == 0
        assert loaded_paths == [str(nested_artifact_dir)]