# Scaling safely

Start with 100 symbols and run the release validator before increasing the batch.

Recommended progression:

1. 100-symbol pilot, manual sample of 20.
2. Second 100-symbol batch, compare error classes and idempotency.
3. Increase to 500-symbol batches only after both pass.

Keep SEC acquisition conservative and sequential. For large universes, download SEC bulk `submissions.zip` nightly and use it for identity/filing discovery; retain per-document archive downloads only for selected filings.

Do not parallelize around the SEC's aggregate fair-access limit. Multiple workers or machines still count toward the same user total.
