from __future__ import annotations

import importlib.metadata
import sys


SUPPORTED_PYTHON = {(3, 13), (3, 14)}
REQUIRED_PACKAGES = {
    "fastapi": "0.136.1",
    "uvicorn": "0.46.0",
    "jsonschema": "4.26.0",
    "pydantic": "2.13.4",
    "starlette": "1.0.0",
    "typing-extensions": "4.15.0",
}


def main() -> int:
    errors: list[str] = []
    python_version = sys.version_info[:2]
    if python_version not in SUPPORTED_PYTHON:
        errors.append(
            f"unsupported Python {python_version[0]}.{python_version[1]}; expected 3.13 or 3.14"
        )
    for package, expected in REQUIRED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"missing package: {package}=={expected}")
            continue
        if actual != expected:
            errors.append(f"package mismatch: {package} expected {expected}, found {actual}")
    if errors:
        for error in errors:
            print(f"[environment] {error}")
        return 1
    print(
        f"[environment] supported Python {python_version[0]}.{python_version[1]} and locked dependencies verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
