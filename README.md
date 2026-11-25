# WhoOwnsAlberta public releases

This repository is the public release boundary for WhoOwnsAlberta.info. It
currently contains no published site. RELEASE_DISABLED records that state;
GitHub Pages remains disabled.

The private, offline builder produces a site/ directory with index.html,
optional articles/<id>.html pages, and manifest.json. A release PR must copy
only those generated files. Run python3 verify_public.py before opening the
PR. The CI job named public-artifact performs the same check on every PR
and on main.

The verifier checks the repository file allowlist, artifact paths, manifest
shape, and SHA-256 digests. It cannot prove that the private source records or
review decisions were valid. The independent reviewer must compare the PR's
entire site/ tree with a build from the pinned private commit, verify the
private decisions for those exact versions, and check that held, excluded,
private, and synthetic material is absent. The PR must give the pinned private
commit and SHA-256 of site/manifest.json; keep decision records and held-item
identities in the private workspace.

To propose the first release, remove RELEASE_DISABLED and add the complete
generated site/ tree in one PR. Do not enable Pages or merge a release until
the required CI check, independent review, dedicated release identity, and
hosting configuration are ready. An approving review for infrastructure does
not approve later content.
