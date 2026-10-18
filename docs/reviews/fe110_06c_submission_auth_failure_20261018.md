# Three06_C static-force jobs: authorized,not submitted

Date:2026-10-18 Asia/Shanghai.

The user requested progress and submission of the previously reviewed three
static-force labels. Their input hashes remain unchanged and canonical local
submission status is`NOT_RESERVED` for all three. Existing local static
preflights and29 tests remain evidence of preparation,not VASP execution.

Before any upload or expensive command,the read-only remote prerequisite
failed with SSH exit255:

`nsgkn_chengdj3@10.68.0.103: Permission denied (publickey,gssapi-keyex,gssapi-with-mic,password).`

One bounded verbose authentication diagnostic establishes:

- TCP/SSH connection is established;this is not a routing timeout.
- The configured ED25519 key file exists and OpenSSH offers its public key.
- The server does not accept that offered key for the configured account.
- No SSH-agent socket is available,but the explicit key is still offered;
  starting an agent is not an evidenced fix for this server-side rejection.
- Password/interactive authentication was not attempted;private-key contents
  were not read,displayed,copied or modified.

No remote scientific command,upload,bsub,job cancellation or model change
occurred. No submission reservation or job ID was created. The actual remote
POTCAR hash could not be checked;the execution gate has not been issued.
Do not interpret this as a VASP failure or modify structure/DFT settings.

Evidence is preserved under
`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_boundary_labels_20261018_v1/`:
`remote_presubmission_check.json`,`ssh_auth_diagnosis.json`,and
`authorized_submission_status.json`.
The exact user/batch scope is recorded in
`archive/fe110_adsorption_validation_20261018/authorization_submit_06c_20261018.md`.

Next: restore key-based authentication for`sunboquan-codex` on the configured
account. Then verify the same input/POTCAR hashes and fresh canonical
SUBMIT_DIAGNOSTIC_VASP gates before submitting exactly these three jobs.
Do not switch to another account or retry unchanged authentication repeatedly.
