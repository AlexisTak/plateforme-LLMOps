# RAG document categories

- `methods/` — organizational techniques (Pomodoro, GTD, time blocking, ...)
- `research/` — official/academic studies about ADHD and related topics. **Informational context only.** These documents are retrieved like any other RAG source and are subject to the same rule as everything else in this project: the model never uses retrieved content to diagnose, prescribe, or give personalized medical advice — see `training/configs/system_prompt.txt`, `datasets/safety/`, and `tests/test_rag_injection.py`. A study snippet can inform a factual answer ("studies suggest X"); it must never become the basis for "you have ADHD" or "you should take Y".
- `product/` — Biscuits Focus product documentation.
- `other/` — anything that doesn't fit the above.

Add documents via the RAG page in the web console (`/rag`) or `POST /api/rag/documents` / `/api/rag/documents/upload`. Rebuild the index after adding documents (`POST /api/rag/reindex` or the "Reconstruire l'index" button).
