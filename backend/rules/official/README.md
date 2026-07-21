# Official ITR artifacts

Do not hand-edit or fabricate these files. Run:

```bash
python scripts/sync_official_itr_artifacts.py
```

The script downloads current configured official schemas, verifies they are JSON,
writes them locally and creates `manifest.json` with SHA-256 hashes. A tax-domain
owner must review the sources/hashes before production activation. The example
manifest is not accepted by the exporter.
