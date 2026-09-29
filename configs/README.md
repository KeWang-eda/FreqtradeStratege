# Configs

This directory contains sanitized configuration templates for the clean-room framework.

## Naming

Use the following pattern:

```text
<scenario>-<framework-or-experiment>.json
```

Current template:

- `freqai/layered-vtech.example.json`

Do not commit API keys, private endpoints, database paths containing secrets, or generated model caches.

## Configuration boundary

- `timeframe`, futures mode, margin mode, fee, leverage, and pairlist belong to the run protocol.
- Feature, label, model, and training changes require a new model identifier.
- A configuration template is not a validated production configuration.
