# Assistant model evaluation

The suite verifies tool selection and that forbidden capabilities are never requested.
It contains only synthetic prompts and must not contain taxpayer data.

Offline evaluation:

```bash
python scripts/evaluate_model.py --responses responses.json
```

Online evaluation against the configured OpenRouter model:

```bash
OPENROUTER_API_KEY=... OPENROUTER_ASSISTANT_MODEL=... \
python scripts/evaluate_model.py --online --output model-evaluation.json
```

A model is not approved for production merely because this starter suite passes.
Expand it with CA-reviewed explanations, citation checks, multilingual prompts, malformed
tool arguments and indirect prompt-injection documents before release.
