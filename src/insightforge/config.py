from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .verifier import VerificationConfig


DEFAULT_CONFIG_PATH = Path(".insightforge.toml")


@dataclass(slots=True)
class PolicyConfig:
    min_confidence: float = 0.65
    require_sources: bool = False
    require_verifiable_sources: bool = False
    fail_on_stderr: bool = True
    block_absolute_language: bool = False
    max_output_chars: int = 20000


@dataclass(slots=True)
class RedactionConfig:
    enabled: bool = True
    mask: str = "[REDACTED]"
    patterns: list[str] = field(
        default_factory=lambda: [
            r"sk-[A-Za-z0-9_\-]+",
            r"AIza[0-9A-Za-z\-_]+",
            r"ghp_[A-Za-z0-9]+",
            r"\b[\w.\-]+@[\w.\-]+\.\w+\b",
            r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
        ]
    )


@dataclass(slots=True)
class StorageConfig:
    sqlite_path: str = ".insightforge/traces.db"


@dataclass(slots=True)
class UpdateConfig:
    enabled: bool = True
    package_name: str = "insightforge"
    check_interval_hours: int = 24


@dataclass(slots=True)
class AppConfig:
    policy: PolicyConfig = field(default_factory=PolicyConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    redaction: RedactionConfig = field(default_factory=RedactionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    updates: UpdateConfig = field(default_factory=UpdateConfig)


def load_config(cwd: Path | None = None) -> AppConfig:
    base = cwd or Path.cwd()
    path = base / DEFAULT_CONFIG_PATH
    config = AppConfig()
    if not path.exists():
        return config

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    policy = payload.get("policy", {})
    verification = payload.get("verification", {})
    redaction = payload.get("redaction", {})
    storage = payload.get("storage", {})
    updates = payload.get("updates", {})

    config.policy = PolicyConfig(
        min_confidence=float(policy.get("min_confidence", config.policy.min_confidence)),
        require_sources=bool(policy.get("require_sources", config.policy.require_sources)),
        require_verifiable_sources=bool(
            policy.get("require_verifiable_sources", config.policy.require_verifiable_sources)
        ),
        fail_on_stderr=bool(policy.get("fail_on_stderr", config.policy.fail_on_stderr)),
        block_absolute_language=bool(
            policy.get("block_absolute_language", config.policy.block_absolute_language)
        ),
        max_output_chars=int(policy.get("max_output_chars", config.policy.max_output_chars)),
    )
    config.verification = VerificationConfig(
        enabled=bool(verification.get("enabled", config.verification.enabled)),
        timeout_seconds=int(
            verification.get("timeout_seconds", config.verification.timeout_seconds)
        ),
        max_urls=int(verification.get("max_urls", config.verification.max_urls)),
        max_bytes=int(verification.get("max_bytes", config.verification.max_bytes)),
        allow_private_hosts=bool(
            verification.get("allow_private_hosts", config.verification.allow_private_hosts)
        ),
    )
    config.redaction = RedactionConfig(
        enabled=bool(redaction.get("enabled", config.redaction.enabled)),
        mask=str(redaction.get("mask", config.redaction.mask)),
        patterns=[str(item) for item in redaction.get("patterns", config.redaction.patterns)],
    )
    config.storage = StorageConfig(
        sqlite_path=str(storage.get("sqlite_path", config.storage.sqlite_path)),
    )
    config.updates = UpdateConfig(
        enabled=bool(updates.get("enabled", config.updates.enabled)),
        package_name=str(updates.get("package_name", config.updates.package_name)),
        check_interval_hours=int(
            updates.get("check_interval_hours", config.updates.check_interval_hours)
        ),
    )
    return config
