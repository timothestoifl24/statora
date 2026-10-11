import os
from importlib.metadata import PackageNotFoundError, version


def _version() -> str:
    # Container images are built with the full release name (e.g. "0.2.0-beta.3"); otherwise use
    # the installed package's version, which comes from pyproject.toml.
    if build := os.environ.get("STATORA_BUILD_VERSION", "").strip():
        return build
    try:
        return version("statora")
    except PackageNotFoundError:  # running from a source tree that isn't installed
        return "0.0.0+unknown"


__version__ = _version()
