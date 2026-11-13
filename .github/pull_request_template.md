## What and why
Ticket / user need:
Spec updated: `specs/...md` (scenarios -> tests)
ADR (if a real alternative was chosen): `docs/adr/...`

## Verification
- [ ] `scripts/verify.sh` green locally (paste the last line)
- [ ] must-catch test from a real example + must-not-flag test for the nearest legitimate case
- [ ] no test assertion weakened to make this pass

## Line-by-line review needed? (tick and review every changed line)
- [ ] Secrets / API keys / tokens
- [ ] Quota or cost (new or more YouTube API calls - units per run stated in the docstring)
- [ ] User or channel data (stored, sent, or logged)

## Scope
One feature, small diff. Anything else goes in its own PR.
