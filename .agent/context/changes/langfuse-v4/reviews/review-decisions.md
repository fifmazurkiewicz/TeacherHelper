# Review decisions

| ID | Severity | Finding | Disposition | Evidence |
| --- | --- | --- | --- | --- |
| LF-1 | Medium | Cached SDK default exporter omitted explicit v4 ingestion header; custom-exporter tests did not cover transport | Fixed | Production constructor now sets x-langfuse-ingestion-version=4. Real default-exporter test asserts endpoint, header and decoded span. Removing header deliberately fails test. Independent reviewer approved final fix. |
