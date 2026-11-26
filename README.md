# WhoOwnsAlberta public releases

This repository is the public release boundary for WhoOwnsAlberta.info.
GitHub Pages deploys only from protected main through the deploy-pages workflow.
The public-artifact job checks every PR and is required for merging. Main
requires an independent approving review.

The first site is a holding page with no research claims. Its holding-v1
manifest and exact HTML digest are pinned in verify_public.py. That profile
permits only site/index.html and site/manifest.json. It does not imply approval
of a research dataset or article. An independent reviewer must inspect the
exact holding page before this release merges.

Later content releases may replace the holding page with the private offline
builder's complete `public-v1` claim/article or `wiki-v1` research-wiki `site/`
output. A public release PR must state the pinned private commit and SHA-256 of
`site/manifest.json`. The reviewer must compare the entire proposed `site/`
tree against a build from that commit, verify the exact private review
decisions, and check that uncleared held details, excluded and private records,
and synthetic material are absent. A cleared, labelled held lead may appear as
an unresolved question. Keep private decision targets, reasons, and held-item
details in the private workspace. The wiki manifest carries only an aggregate
digest for factual decisions, never private research paths or IDs.

Run python3 -m unittest discover -s tests and python3 verify_public.py before
opening a PR. The verifier checks the public file allowlist, artifact paths,
manifest shape, output set, and SHA-256 digests. It cannot make editorial or
legal approval decisions. Changed output or dependencies need fresh review.
