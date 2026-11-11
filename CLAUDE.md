# Asset Arena Wire

Sports business press release wire. Static site on GitHub Pages, built by `build.py` (stdlib only) from `releases/*.json` into `_site/` (gitignored). See README.md for the release format.

Rules:
- Never use em dashes or en dashes in any copy, code comments or release text. The build rejects them in releases.
- Pricing: $199 per release, $1,200 per year Founding Member, paid after approval. Pricing copy lives in `config.json`.
- Keep the build dependency free. Run `python3 build.py --check` and `python3 build.py` before committing.
- Never publish a release that was not submitted and approved by the named organization.
