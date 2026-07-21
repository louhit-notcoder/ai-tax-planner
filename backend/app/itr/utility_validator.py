from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UtilityValidationResult:
    configured: bool
    passed: bool
    errors: list[dict]
    stdout: str = ""
    stderr: str = ""


class OfficialUtilityValidationAdapter:
    """Adapter for a locally installed/approved official utility validation command.

    Set ITR_UTILITY_VALIDATION_COMMAND to a command template containing
    ``{input}`` and optionally ``{output}``. The command must exit 0 only when
    validation passes. This keeps code ready without pretending the public GUI
    utility exposes a stable server-side CLI.
    """

    def __init__(self, command_template: str | None = None):
        self.command_template = command_template or os.getenv("ITR_UTILITY_VALIDATION_COMMAND", "").strip()

    def validate(self, payload: dict) -> UtilityValidationResult:
        if not self.command_template:
            return UtilityValidationResult(False, False, [{"code": "UTILITY_VALIDATOR_NOT_CONFIGURED", "message": "Official utility validation command is not configured."}])
        with tempfile.TemporaryDirectory() as temp:
            input_path = Path(temp) / "return.json"
            output_path = Path(temp) / "validation.json"
            input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            command = self.command_template.format(input=str(input_path), output=str(output_path))
            process = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=180, check=False)
            errors = []
            if output_path.exists():
                try:
                    output = json.loads(output_path.read_text(encoding="utf-8"))
                    errors = output.get("errors", output if isinstance(output, list) else [])
                except Exception:
                    errors = [{"code": "UTILITY_OUTPUT_INVALID", "message": output_path.read_text(encoding="utf-8", errors="replace")[:2000]}]
            elif process.returncode != 0:
                errors = [{"code": "UTILITY_VALIDATION_FAILED", "message": (process.stderr or process.stdout or "Validation command failed")[:2000]}]
            return UtilityValidationResult(True, process.returncode == 0 and not errors, errors, process.stdout[-4000:], process.stderr[-4000:])
