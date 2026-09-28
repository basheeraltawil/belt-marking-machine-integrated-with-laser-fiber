# belt_marking_vision

Optional AI modules. **None of them is in the safety path.** They report or suggest, and the
controller decides. Details: [docs/AI_FEATURES.md](../../../docs/AI_FEATURES.md).

| Module | Entry | What |
|---|---|---|
| Vision QA | `vision_qa_node` | inspects every label (presence, contrast, position, optional OCR) → `quality/result`; camera mode (Gazebo/real) or synthetic mode |
| Anomaly detection | `anomaly_node` | robust drift detection on logged cycle times → `maintenance/drift` → W-702 |
| Operator assistant | `assistant "question"` | offline BM25 retrieval over the docs + exact alarm answers; optional local LLM (Ollama). Read-only |
| NL job entry | `nl_job.parse_job_text` (UI: Job setup → *Describe job…*) | "200 pieces of 30 mm belt, cut each" → form draft, operator confirms |
