from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from ..config import get_settings


@dataclass(frozen=True)
class SchemaArtifact:
    form_code: str
    version: str
    path: Path
    sha256: str
    source_url: str


class OfficialSchemaRegistry:
    """Pinned official schema store.

    Production export is disabled unless a locally pinned schema exists and its hash
    appears in manifest.json. This avoids silently using a changed portal schema.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().schema_root
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.root / "manifest.json"

    def manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"artifacts": {}}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def get(self, form_code: str) -> SchemaArtifact:
        item = self.manifest().get("artifacts", {}).get(form_code)
        if not item:
            raise RuntimeError(f"Official {form_code} schema is not pinned. Run scripts/sync_official_itr_artifacts.py.")
        path = self.root / item["filename"]
        if not path.exists():
            raise RuntimeError(f"Pinned schema file is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise RuntimeError(f"Pinned schema hash mismatch for {form_code}")
        return SchemaArtifact(form_code, item["version"], path, digest, item["source_url"])

    def load_schema(self, form_code: str) -> dict:
        artifact = self.get(form_code)
        return json.loads(artifact.path.read_text(encoding="utf-8-sig"))

    def sync(self, form_code: str, url: str, version: str, timeout: int = 60) -> SchemaArtifact:
        response = requests.get(url, timeout=timeout, headers={"User-Agent": "GreenPapayaSchemaSync/3.0"})
        response.raise_for_status()
        content = response.content
        schema_bytes, filename = self._extract_json(content, response.headers.get("content-type", ""), form_code)
        path = self.root / filename
        path.write_bytes(schema_bytes)
        digest = hashlib.sha256(schema_bytes).hexdigest()
        manifest = self.manifest()
        manifest.setdefault("artifacts", {})[form_code] = {
            "filename": filename,
            "version": version,
            "sha256": digest,
            "source_url": url,
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return SchemaArtifact(form_code, version, path, digest, url)

    @staticmethod
    def _extract_json(content: bytes, content_type: str, form_code: str) -> tuple[bytes, str]:
        if content[:2] == b"PK" or "zip" in content_type.lower():
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = [name for name in archive.namelist() if name.lower().endswith(".json") and "schema" in name.lower()]
                if not names:
                    names = [name for name in archive.namelist() if name.lower().endswith(".json")]
                if not names:
                    raise RuntimeError("Official archive contains no JSON schema")
                name = sorted(names, key=len)[0]
                data = archive.read(name)
                json.loads(data.decode("utf-8-sig"))
                return data, f"{form_code}_{Path(name).name}"
        json.loads(content.decode("utf-8-sig"))
        return content, f"{form_code}_official_schema.json"
