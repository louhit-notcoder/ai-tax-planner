# Staging DAST harness

Run only against an environment you own and have explicitly authorised:

```bash
STAGING_URL=https://staging.example.com scripts/run_zap_baseline.sh
```

The script runs the OWASP ZAP baseline container and stores HTML, JSON and Markdown
reports under `security-reports/zap`. Baseline scanning is not a substitute for the
mandatory independent authenticated penetration test.
