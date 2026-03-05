"""Utility functions for session management in the GUI."""

from pathlib import Path


def resolve_video_paths(
    sources_in_file: list[str],
    video_dir: str,
) -> tuple[dict[str, str], list[str]]:
    """
    Resolve CSV source names to local file paths.

    This is extracted from ValidationTab.open_session for testability.

    Args:
        sources_in_file: Source file values from the CSV.
        video_dir: Local directory to search for matching videos.

    Returns:
        Tuple of (resolved_mapping, s3_sources) where resolved_mapping
        maps source names to local paths and s3_sources lists any S3
        URIs that couldn't be resolved.
    """
    video_dir_path = Path(video_dir)
    resolved: dict[str, str] = {}
    s3_sources: list[str] = []

    for source in sources_in_file:
        if source.startswith("s3://"):
            s3_sources.append(source)
            continue

        candidate = video_dir_path / Path(source).name
        if candidate.exists():
            resolved[source] = str(candidate)

    return resolved, s3_sources
