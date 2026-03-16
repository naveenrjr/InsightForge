from __future__ import annotations


DEFAULT_CONFIG_TEMPLATE = """[policy]
min_confidence = 0.85
require_sources = true
require_verifiable_sources = true
fail_on_stderr = true
block_absolute_language = true
max_output_chars = 20000

[redaction]
enabled = true
mask = "[REDACTED]"
patterns = [
  "sk-[A-Za-z0-9_\\\\-]+",
  "AIza[0-9A-Za-z\\\\-_]+",
  "ghp_[A-Za-z0-9]+",
  "\\\\b[\\\\w.\\\\-]+@[\\\\w.\\\\-]+\\\\.\\\\w+\\\\b",
  "Bearer\\\\s+[A-Za-z0-9\\\\-._~+/]+=*",
]

[storage]
sqlite_path = ".insightforge/traces.db"

[verification]
enabled = true
timeout_seconds = 3
max_urls = 5
max_bytes = 120000
allow_private_hosts = false

[updates]
enabled = true
package_name = "insightforge"
check_interval_hours = 24
"""
