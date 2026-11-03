# Price fixtures

The tencent US/HK/CN and Nasdaq US sample files are byte-for-byte copies of G1 recordings, including their original provenance. US Tencent contains only two rows (one from 2011), not 30. HK/CN each retain 30 rows, including observed action metadata and decimal volume strings. No fabricated row is appended to a real recording.

`prices_nasdaq_250_clipped.sample.json` retains the latest 30 rows of the coordinator's 250-row AAPL response. Access was 2026-11-03T04:17:17.741074Z, HTTP 200, URL and original response SHA-256 are in `_provenance`. The full response remains only in `/tmp/jev-n10-nasdaq_aapl_250.json`. Replaying the clip is a mock parser check, not a new live request or a 250-row continuity proof.

`prices_tencent_bad.json`, `prices_invalid_ohlc.json` and `prices_synthetic.py` are explicitly synthetic. The encoding and error transport variants are created in tests. Decimal precision is checked before converting reliable integers to `Bar.volume`; units are not inferred. `qfqday` maps to `adj_close=close` per D-04, but split/dividend adjustment semantics remain unverified. `day` and Nasdaq use `adj_close=None`.

NYSE date verification is documented separately in `resources/calendars/SOURCES.md`. SEC, source adjustment, terms and rate gates remain unpassed.
