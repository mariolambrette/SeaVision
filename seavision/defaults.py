"""Helpers for packaged default configuration files."""

from importlib.resources import files
from pathlib import Path

_DEFAULT_PIPELINE_CONFIG = files("seavision").joinpath("resources/default.yaml")

def default_pipeline_config_text() -> str:
    """Return the packaged default pipeline configuration as text."""
    return _DEFAULT_PIPELINE_CONFIG.read_text(encoding="utf-8")

def write_default_pipeline_config(
    destination: str | Path,
    overwrite: bool = False,
) -> Path:
    """
    Write the packaged default pipeline configuration to a user-selected path.

    Args:
        destination: Output path for the YAML file.
        overwrite: If True, replace an existing file.

    Returns:
        The resolved output path.

    Raises:
        FileExistsError: If the file already exists and overwrite is False.
    """
    output_path = Path(destination)

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(default_pipeline_config_text(), encoding="utf-8")
    return output_path.resolve()