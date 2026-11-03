# SEC synthetic fixtures

Every payload in this directory is synthetic, authored for D-03 offline tests
from the field and selection rules in docs/07 and D-03. None is a recording
or evidence of real SEC acceptance precision, index structure or availability.
The fictional issuer is Zenith Arc Robotics Inc. (ZZAR), with synthetic CIK
0001234567 and accessions. Tests never issue requests using these identifiers.

- submissions_0001234567.synthetic.json: 15 constructed rows and 16 parallel
  arrays; three supported and two excluded form types, July 16-30, 2026.
- filing_index_8k_ex99.synthetic.html: constructed four-column table, primary
  document, five HTML EX-99 exhibits, XML and PDF skipped documents.
- filing_*.synthetic.html: constructed cover, press release and Inline XBRL.
- error_*.synthetic.http: handwritten HTTP status/Retry-After examples.

G1-US has no submissions/index recording because no real contact email was
configured. These fixtures do not fill that gap. Real integration is NOT_RUN.
Mock-only email addresses are never sent to a real SEC transport.
