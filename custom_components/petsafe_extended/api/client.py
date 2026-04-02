"""Helpers for loading and instantiating the external petsafe-api library."""

from __future__ import annotations

from functools import partial
import importlib
from importlib import metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, cast

from packaging.requirements import InvalidRequirement, Requirement

from custom_components.petsafe_extended.const import CONF_REFRESH_TOKEN, DOMAIN, LOGGER
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_EMAIL, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.loader import async_get_integration
from homeassistant.requirements import RequirementsNotFound, _async_get_manager, pip_kwargs


def _has_distribution(distribution_name: str) -> bool:
    """Return whether a distribution is installed in the current interpreter."""
    try:
        metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return False
    return True


def _get_distribution_top_levels(distribution_name: str) -> list[str]:
    """Return top-level module names advertised by a distribution."""
    try:
        dist = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return []

    top_level = dist.read_text("top_level.txt")
    if not top_level:
        return []

    return [line.strip() for line in top_level.splitlines() if line.strip()]


def _ensure_deps_path(config_dir: str) -> None:
    """Ensure Home Assistant's config deps directory is importable."""
    _ensure_import_path(str(Path(config_dir) / "deps"))


def _ensure_import_path(import_path: str) -> None:
    """Ensure an import root is available on sys.path."""
    if import_path not in sys.path:
        sys.path.insert(0, import_path)


def _invalidate_import_state() -> None:
    """Refresh Python's import caches after runtime requirement installation."""
    importlib.invalidate_caches()
    sys.path_importer_cache.clear()


def _get_distribution_root(distribution_name: str, module_name: str) -> str | None:
    """Return the import root for an installed distribution."""
    try:
        dist = metadata.distribution(distribution_name)
    except metadata.PackageNotFoundError:
        return None

    module_init = Path(str(dist.locate_file(f"{module_name}/__init__.py")))
    if module_init.exists():
        return str(module_init.parent.parent)

    return None


def _install_requirement_to_target(
    requirement: str,
    config_dir: str,
    target: str,
    module_name: str,
) -> bool:
    """Install a requirement into an explicit target and verify the module files exist."""
    try:
        requirement_details = Requirement(requirement)
    except InvalidRequirement:
        return False

    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)

    install_kwargs = pip_kwargs(config_dir)
    install_args = [
        *_get_uv_command(),
        "pip",
        "install",
        "--quiet",
        requirement,
        "--index-strategy",
        "unsafe-first-match",
        "--upgrade",
        "--target",
        target,
    ]
    if constraints := install_kwargs.get("constraints"):
        install_args += ["--constraint", constraints]

    env = os.environ.copy()
    if timeout := install_kwargs.get("timeout"):
        env["HTTP_TIMEOUT"] = str(timeout)

    result = subprocess.run(
        install_args,
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )
    if result.returncode != 0:
        error_output = result.stderr.strip() or result.stdout.strip()
        LOGGER.warning(
            "Explicit petsafe-api install into %s failed with exit code %s: %s",
            target,
            result.returncode,
            error_output,
        )
        return False

    normalized_name = requirement_details.name.replace("-", "_")
    module_init = target_path / module_name / "__init__.py"
    dist_info_exists = any(target_path.glob(f"{normalized_name}-*.dist-info"))
    if not module_init.exists() and not dist_info_exists:
        LOGGER.warning(
            (
                "Explicit petsafe-api install into %s exited successfully but left no module files. "
                "python=%s sys_executable=%s sys_prefix=%s stdout=%s stderr=%s"
            ),
            target,
            _get_runtime_python(),
            sys.executable,
            sys.prefix,
            result.stdout.strip() or "<empty>",
            result.stderr.strip() or "<empty>",
        )

    return module_init.exists() or dist_info_exists


def _get_runtime_deps_path() -> str:
    """Return an explicit runtime dependency directory outside the workspace mount."""
    return str(Path.home() / ".cache" / DOMAIN / "deps")


def _get_runtime_python() -> str:
    """Return the Home Assistant runtime interpreter path."""
    argv0_path = Path(sys.argv[0]).resolve()
    candidates = [
        argv0_path.with_name("python3"),
        argv0_path.with_name("python"),
        argv0_path.with_name("python.exe"),
        Path(sys.prefix) / "bin" / "python3",
        Path(sys.prefix) / "bin" / "python",
        Path(sys.prefix) / "Scripts" / "python.exe",
        Path(sys.executable),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return sys.executable


def _get_uv_command() -> list[str]:
    """Return the best available uv command."""
    if uv_path := shutil.which("uv"):
        return [uv_path]

    return [_get_runtime_python(), "-m", "uv"]


def _run_uv_command(*args: str) -> str | None:
    """Return stdout from a uv command for the current interpreter."""
    try:
        result = subprocess.run(
            [*_get_uv_command(), *args],
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return None

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    return output or None


def _get_uv_install_location(distribution_name: str) -> str | None:
    """Return uv's reported installation location for a distribution."""
    if not (output := _run_uv_command("pip", "show", distribution_name)):
        return None

    for line in output.splitlines():
        if line.startswith("Location:"):
            location = line.partition(":")[2].strip()
            if location:
                return location

    return None


def _get_uv_cache_dir() -> Path | None:
    """Return the active uv cache directory for the current interpreter."""
    if not (output := _run_uv_command("cache", "dir")):
        return None

    cache_dir = Path(output)
    return cache_dir if cache_dir.exists() else None


def _get_uv_archive_parent(cache_dir: Path, module_name: str) -> str | None:
    """Return the extracted uv archive path containing a module, if present."""
    for archive_root in sorted(cache_dir.glob("archive-v*")):
        for module_init in archive_root.glob(f"*/{module_name}/__init__.py"):
            return str(module_init.parent.parent)
    return None


async def async_import_petsafe(hass: HomeAssistant) -> Any:
    """Ensure the petsafe dependency is installed before importing it."""
    integration = await async_get_integration(hass, DOMAIN)
    manager = _async_get_manager(hass)
    _ensure_deps_path(hass.config.config_dir)
    deps_path = await hass.async_add_executor_job(_get_runtime_deps_path)
    requirements_error: RequirementsNotFound | None = None

    if not await hass.async_add_executor_job(_has_distribution, "petsafe-api"):
        for requirement in integration.requirements:
            manager.is_installed_cache.discard(requirement)
            manager.install_failure_history.discard(requirement)

    try:
        await cast(Any, manager.async_process_requirements)(
            integration.domain,
            integration.requirements,
            integration.is_built_in,
        )
    except RequirementsNotFound as err:
        requirements_error = err
        LOGGER.warning(
            "Home Assistant requirement processing did not yield an importable petsafe-api distribution; "
            "trying explicit deps installation"
        )

    await hass.async_add_executor_job(_invalidate_import_state)

    try:
        return await hass.async_add_executor_job(importlib.import_module, "petsafe")
    except ModuleNotFoundError as err:
        candidate_roots = [
            await hass.async_add_executor_job(_get_distribution_root, "petsafe-api", "petsafe"),
            await hass.async_add_executor_job(_get_uv_install_location, "petsafe-api"),
        ]

        for import_root in candidate_roots:
            if not import_root:
                continue

            _ensure_import_path(import_root)

            await hass.async_add_executor_job(_invalidate_import_state)
            try:
                return await hass.async_add_executor_job(importlib.import_module, "petsafe")
            except ModuleNotFoundError:
                continue

        cache_dir: Path | None = await hass.async_add_executor_job(_get_uv_cache_dir)
        if cache_dir and (
            archive_parent := await hass.async_add_executor_job(_get_uv_archive_parent, cache_dir, "petsafe")
        ):
            _ensure_import_path(archive_parent)
            await hass.async_add_executor_job(_invalidate_import_state)
            return await hass.async_add_executor_job(importlib.import_module, "petsafe")

        top_levels = await hass.async_add_executor_job(_get_distribution_top_levels, "petsafe-api")
        for module_name in top_levels:
            if module_name == "petsafe":
                continue
            try:
                module = await hass.async_add_executor_job(importlib.import_module, module_name)
            except ModuleNotFoundError:
                continue

            LOGGER.warning("Imported petsafe-api using top-level module '%s'", module_name)
            return module

        LOGGER.warning("Attempting explicit petsafe-api install into %s", deps_path)
        async with manager.pip_lock:
            install_ok = True
            for requirement in integration.requirements:
                manager.is_installed_cache.discard(requirement)
                manager.install_failure_history.discard(requirement)
                installed = await hass.async_add_executor_job(
                    _install_requirement_to_target,
                    requirement,
                    hass.config.config_dir,
                    deps_path,
                    "petsafe",
                )
                if installed:
                    manager.is_installed_cache.add(requirement)
                    continue

                manager.install_failure_history.add(requirement)
                install_ok = False

            if install_ok:
                _ensure_import_path(deps_path)
                await hass.async_add_executor_job(_invalidate_import_state)
                return await hass.async_add_executor_job(importlib.import_module, "petsafe")

        LOGGER.warning(
            (
                "petsafe-api installation did not yield an importable 'petsafe' module; "
                "distribution_root=%s, uv_install_location=%s, uv_cache_dir=%s, home=%s"
            ),
            candidate_roots[0],
            candidate_roots[1],
            cache_dir,
            Path.home(),
        )
        if requirements_error is not None:
            raise requirements_error from err
        raise


async def async_create_auth_client(
    hass: HomeAssistant,
    petsafe: Any,
    email: str,
) -> Any:
    """Create an unauthenticated client for requesting and exchanging auth codes."""
    return await hass.async_add_executor_job(partial(petsafe.PetSafeClient, email=email))


def create_petsafe_client(
    hass: HomeAssistant,
    petsafe: Any,
    entry: ConfigEntry,
) -> Any:
    """Create an authenticated petsafe-api client for a config entry."""
    return petsafe.PetSafeClient(
        entry.data.get(CONF_EMAIL),
        entry.data.get(CONF_TOKEN),
        entry.data.get(CONF_REFRESH_TOKEN),
        entry.data.get(CONF_ACCESS_TOKEN),
        client=get_async_client(hass),
    )
