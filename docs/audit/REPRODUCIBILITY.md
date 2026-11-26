# Reproduce the proposed release

Use the review ZIP instructions and patches to reconstruct the exact Git tree in a new checkout. The tested environment is Windows CPython 3.13.9 with the versions in v31/requirements.lock. Install these into a separate environment from a trusted offline wheelhouse. The environment file records interpreter and host information.

From the reconstructed checkout, build a wheel from the v31 subdirectory with `python -m pip wheel --no-index --no-deps --no-build-isolation ./v31 -w EXTERNAL_WHEELS`. Install that wheel in the isolated environment with `python -m pip install --no-index --no-deps WHEEL_PATH`. The installed package sbq123_v31 carries the role inventories, scientific sources, release tools and offline evidence. The installer does not globally expose either role's scripts package.

Use `python -I -B -m sbq123_v31.prepare NEW_EXTERNAL_PAIR` to materialize and check resource bytes. For each role run `python -I -B -m sbq123_v31.regression PAIR ROLE NEW_EXTERNAL_OUTPUT`. For a comparison run `python -I -B -m sbq123_v31.compare PAIR REQUEST EXPECTED_REQUEST_SHA256`. Use a fresh output directory on each invocation. Both role directories must stay adjacent for the isolated MKM replay. Some original native execution receipts retain host-bound paths; archival replay does not authorize new native execution.

## Independent role wheels

From the clean release checkout, use the locked Python environment and run
`python -B v31/build_release.py mkm EXTERNAL_WHEELS` and
`python -B v31/build_release.py kmc EXTERNAL_WHEELS`. Each build stages the
selected role's verified Python manifest, its declared runtime resources, and
the identity files used by the installed readers. Runtime resources absent
from the projection come from this checkout. The lifecycle implementation is
a common runtime module. The role verifier is part of both hash-bound source
inventories, and the point-reader entry belongs to MKM. Test suites and the
build hook are excluded from the wheel.

Install each wheel from its role subdirectory in its own environment. The
distributions retain the historical project name and console scripts. Supply
reviewed case files separately for scientific operations. For paired archive
replay, keep the two evidence directories adjacent, install the matching wheel
into each role directory (pip --target), and supply the MKM role directory
explicitly to the KMC comparison CLI. This is a data and subprocess boundary.
The ordinary console entry points work from a separate installation; commands
that manage a repository require an explicit repository context.
