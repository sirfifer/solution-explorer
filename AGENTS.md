# Durable work is mandatory

Owner instruction, 2026-09-08: work represents invested time and sometimes paid
AI output. It must survive a reboot. Never put a working checkout, uncommitted
changes, analysis database, generated result, model response, run ledger, report,
or the only copy of validation evidence in a transient or automatically cleaned
directory. This includes /tmp, /private/tmp, /var/tmp, TMPDIR, system cache
directories, and temporary container filesystems.

Choose a persistent project directory before starting work. Resolve symlinks and
check the actual storage location. Store private local artifacts in
`.local-private/` and use durable worktrees. Persist run commands, input revisions,
logs, outputs, completion status, and restart instructions alongside each run.
Checkpoint substantial code changes in Git and preserve expensive generated
artifacts separately; Git does not protect untracked or ignored files.

Do not rely on a surviving process, terminal session, transcript, or a later copy
out of temporary storage. Persist results as they are produced. Reboot recovery
must distinguish completed, interrupted, and unverified work and validate saved
artifacts before resuming. Never overwrite the sole surviving recovery evidence.

Operating-system temporary scratch is acceptable only for automatically
recreatable internal mechanics that contain no unique work product. Keep the
authoritative inputs, outputs, state, and evidence on durable storage throughout.
