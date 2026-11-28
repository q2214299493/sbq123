"""Release-owned content identity of installed scientific configuration."""

TRUST_SHA256 = "9520bb05adb7b10afec4374bf970ab726a7a1e431ecd01b23fd44c431ac1e1da"

SCHEMAS_SHA256 = "978386524e3c24fda0fef6c589b01c5ae2a9a9cdb398cdd892f6623d6dec514c"

# Detached mass-calibration approvals installed by independent release review.
MKM_MASS_APPROVALS: frozenset[str] = frozenset()

# Only reviews independently accepted by the deployment can import returned network revisions.
DISCOVERY_RETURN_APPROVALS: frozenset[str] = frozenset()

# Producer result IDs from the 011b62c trace-correction numerical archive (Windows).
REACTOR_CONTROL_RESULTS = frozenset({
    "bd46dc8bf44c99f026fb4fba0c162bc952e45fbfe7bfeb93be276367d181c8b7",
    "a3f78508a1ba041ba9fd06c6961837a876b42c9c3da1357c30a89fe622ec5593",
})
