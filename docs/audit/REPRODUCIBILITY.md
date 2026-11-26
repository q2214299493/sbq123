# Reproduce the proposed release

Use the review ZIP instructions and patches to reconstruct the exact Git tree in a new checkout. The tested environment is Windows CPython 3.13.9 with the versions in v31/requirements.lock. Install these into a separate environment from a trusted offline wheelhouse. The environment file records interpreter and host information.

From the reconstructed checkout, build a wheel from the v31 subdirectory with `python -m pip wheel --no-index --no-deps --no-build-isolation ./v31 -w EXTERNAL_WHEELS`. Install that wheel in the isolated environment with `python -m pip install --no-index --no-deps WHEEL_PATH`. The installed package sbq123_v31 carries the role inventories, scientific sources, release tools and offline evidence. The installer does not globally expose either role's scripts package.

Use `python -I -B -m sbq123_v31.prepare NEW_EXTERNAL_PAIR` to materialize and check resource bytes. For each role run `python -I -B -m sbq123_v31.regression PAIR ROLE NEW_EXTERNAL_OUTPUT`. For a comparison run `python -I -B -m sbq123_v31.compare PAIR REQUEST EXPECTED_REQUEST_SHA256`. Use a fresh output directory on each invocation. Both role directories must stay adjacent for the isolated MKM replay. Some original native execution receipts retain host-bound paths; archival replay does not authorize new native execution.
