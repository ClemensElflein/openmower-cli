from importlib.metadata import version, PackageNotFoundError

__all__ = ["__version__"]

try:
    __version__ = version("openmower-cli")
except PackageNotFoundError:
    # Fallback when running from source without installation; try setuptools_scm if available
    try:
        from setuptools_scm import get_version as _get_version  # type: ignore

        __version__ = _get_version(root="..", relative_to=__file__)
    except Exception:
        __version__ = "0.0.0.dev0"
