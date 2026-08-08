# MSSQL Lab Build History & Lessons Learned

> How the Always On AG build now running on `devops_VM1`/`devops_VM2` actually
> came together — including the two architecture reversals, the SSH/inventory
> churn, and the eight real bugs live testing surfaced. Reconstructed from git
> history (`git log --oneline --reverse`), `python-fastapi-mssql/CHANGELOG.md`,
> and `docs/changelog/mssql-build-changelog.md`. Companion to
> [`mssql-rewind-and-teardown-implementation.md`](mssql-rewind-and-teardown-implementation.md),
> which is the forward-looking plan; this one is the retrospective.

## Timeline

| Date | Commit | What happened |
|---|---|---|
| — | `5f59b6d`/`5b740ad`/`7bcd447`/`89b58d8` | Repo bootstrap: merged GitLab + GitHub histories into one tree |
| 2026-05-03 | `af52ce5` | **Reversal #1**: ripped Ansible out of FastAPI, replaced with raw Paramiko SSH (`python_deployer.py`) |
| 2026-05 → 2026-07 | 7× "Update VMware GitLab AWX setup documentation", 3× "Update file hosts.ini" | Iterating the lab topology docs and inventory to match the real VMware NAT IPs/hostnames |
| 2026-07-19 | `42206e8` | **Reversal #2**: brought Ansible back into FastAPI — this time as its own embedded tree (`python-fastapi-mssql/ansible/`), decoupled from the AWX tree |
| 2026-07-25 | `14e5e2b` | Moved dev onto VM1 itself via Remote-SSH; switched `ansible_user` from `root` to `devops` |
| 2026-07-25 | `431f656` | Session handoff note recording the move to VM1 |
| 2026-08-01 | `54b09f0` | Added `mssql_build` role + `full-ag`/`alwayson` endpoints; fixed the SSH key path from a Windows Git-Bash path to a real Linux path |
| 2026-08-01/02 | (`mssql-build-changelog.md`) | First live run of the new `build` endpoint hit an SSH permission failure against vm1 |
| 2026-08-02 | `90e8955` | Found and fixed an accidental **duplicated role directory**; reconciled docs that still described the retired SSH architecture |
| 2026-08-02 | `d5763a3` | **The big one** — live-tested the full AG workflow end to end and fixed 8 real bugs static review had missed |
| 2026-08-02 | `68bf1cb` | Added `ansible.cfg` `log_path` — previously Ansible output only lived in memory or terse `app.log` lines |
| 2026-08-02 | `86653c9` | Documented that VM1 is both a target *and* the controller — "remote" logs were actually local files |
| 2026-08-02 | `a823077` | Added the architecture/swim-lane diagram |

## Phase 1 — First attempt: FastAPI calling the shared Ansible tree

The very first `python-fastapi-mssql/app/ansible_runner.py` didn't have its own
playbooks — it pointed `ANSIBLE_INVENTORY`/`ANSIBLE_PLAYBOOK_DIR` at the
**shared** `ansible-mssql-deploy/` tree (the same one AWX uses). One set of
playbooks, two front ends.

**Why it didn't last:** development happened on a Windows workstation
(`C:\Users\mozy\devops`), and `ansible-playbook` needs a POSIX control node —
it doesn't run natively on Windows. Shelling out to it from FastAPI on Windows
was the wrong tool for where the code was actually running at the time.

## Phase 2 — Reversal #1: native Python SSH (`af52ce5`, 2026-05-03)

Deleted `ansible_runner.py` entirely and added `python_deployer.py` — a
343-line Paramiko SSH/SFTP implementation that ran raw shell commands over SSH
instead of invoking Ansible. Its own docstring states the reasoning directly:

> "This module intentionally does not call Ansible. It uses SSH/SFTP from
> Python so the FastAPI service can be operated as a lightweight API path
> while GitLab/AWX remain the Ansible-driven path."

So this wasn't purely the Windows problem — it was also a deliberate call to
give the lightweight API its own non-Ansible code path, separate from the
enterprise AWX path. Same commit also "hardened" the `ansible-mssql-deploy`
role's `install.yml`/`backup.yml`/`restore.yml`/`adventureworks.yml` tasks
directly, since that tree was now the sole owner of the Ansible-driven path.

**Lesson:** `python_deployer.py` is still in the repo today
(`python-fastapi-mssql/app/python_deployer.py`) — nothing currently imports
it (`routes/deploy.py` wires to `deployer.py`'s `AnsibleMssqlDeployer`
instead), but it's dead code from this phase, not a typo. Don't wire new
routes to it without checking first.

## Phase 3 — Chasing the real lab topology (May–July 2026)

Seven consecutive "Update VMware GitLab AWX setup documentation" commits and
three "Update file hosts.ini" commits — no code changes, just getting the
actual VM IPs (`192.168.70.128/129/130`), hostnames (`devops_AWX`/`devops_VM1`/
`devops_VM2`), and the GitLab-source/GitHub-mirror split written down
correctly. Worth noting only because it shows how much of this kind of lab
work is just pinning down ground truth about the environment before any
playbook can be trusted — the code churn that follows (Phases 4–8) all
assumes this inventory is now accurate.

## Phase 4 — Reversal #2: Ansible comes back, this time embedded (`42206e8`, 2026-07-19)

Once development moved onto VM1 itself (a real Linux box — see Phase 5), the
Windows-control-node problem from Phase 1 disappeared, and Ansible's
idempotency/structure won out over hand-rolled SSH command lists. But instead
of pointing back at the shared `ansible-mssql-deploy/` tree, this commit gave
`python-fastapi-mssql/` its **own** `ansible/` directory — full `roles/`,
`playbooks/`, `inventory/` — deliberately decoupled from the AWX tree so the
two paths could evolve independently. This is the origin of the "two diverged
Ansible trees" architecture documented in `CLAUDE.md` today: it wasn't an
accident, it was the second reversal's explicit design choice, later confirmed
by `90e8955`'s "reconcile stale docs" pass and never merged back together.

`ansible_runner.py` came back too, but much simpler (87 lines vs. the original
213) — just `subprocess.run(["ansible-playbook", ...])` with structured
result capture, no attempt to re-implement what Ansible already does.

## Phase 5 — Moving development onto VM1 (`14e5e2b`, 2026-07-25)

`SESSION_HANDOFF.md` records the actual move: repo cloned onto
`/home/devops/devops/my-devops-project` on VM1, a Python 3.9 venv created
there, VS Code opened via Remote-SSH. This commit's inventory changes flow
directly from that move: `ansible_user` switched from `root` to `devops`
(root SSH wasn't the intended lab account), and `ansible_runner.py` was
hardened to resolve the `ansible-playbook` executable across different
environments (`shutil.which`, then a Windows Scripts-dir fallback still kept
for anyone running the FastAPI side from Windows against the VMs).

## Phase 6 — Build role + AG endpoints, and a path format bug (`54b09f0`, 2026-08-01)

Added the `mssql_build` role (a separate, parallel install flow — see
`CLAUDE.md` for why it duplicates some of `mssql`'s `install.yml`) and wired
up `full-ag`/`alwayson` in `deployer.py`/`routes/deploy.py`. Also fixed
`ansible_ssh_private_key_file` in `hosts.ini`, which was still a Windows
Git-Bash-style path (`/c/Users/mozy/.ssh/id_rsa`) left over from before the
move to VM1 — changed to the real Linux path `/home/devops/.ssh/id_rsa`.

**Then the first live run of `/deploy/build` failed anyway** — recorded in
`docs/changelog/mssql-build-changelog.md`'s "Practical execution log":

```
fatal: [vm1]: UNREACHABLE! => {"changed": false, "msg": "Failed to connect
to the host via ssh: devops@192.168.70.129: Permission denied
(publickey,gssapi-keyex,gssapi-with-mic,password).", "unreachable": true}
```

vm2 succeeded (directories created, `mssql` user created); vm1 failed. Root
cause: fixing the key *path* wasn't enough — the control host's public key had
never actually been added to `devops`'s `~/.ssh/authorized_keys` **on vm1
specifically**. Easy to miss because VM1 is both a deployment target and the
controller — it's tempting to assume "the controller already has its own
keys sorted" when in fact the controller-to-vm1 SSH hop needs the same
`ssh-copy-id` setup as the controller-to-vm2 hop. Fixed with:

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub devops@192.168.70.129
```

## Phase 7 — Found a silently duplicated role (`90e8955`, 2026-08-02)

Ansible resolves `roles:`/`include_role:` paths relative to the *playbook's
own directory* when no `ansible.cfg` `roles_path` override exists. Nothing in
`python-fastapi-mssql/ansible.cfg` set one at the time, so
`ansible/playbooks/roles/mssql_build/` had silently become a **second,
independently-editable physical copy** of `ansible/roles/mssql_build/` —
whichever one a given playbook actually resolved to depended on where you
were looking from, and edits to one didn't touch the other.

**Fix:** replaced the duplicate directory with a symlink
(`ansible/playbooks/roles -> ../roles`), verified with `--syntax-check`
against all four playbooks that existed at the time.

Same commit also added `tags: always` to every `include_tasks` step in
`roles/mssql/tasks/main.yml`, so that invoking the role with a `--tags`
filter (as `alwayson.yml`/`backup.yml` do via `include_role: tasks_from:`)
wouldn't skip sub-task files entirely — an attempt to make tag filtering
reliable. (Phase 8 found this fix wasn't actually sufficient — see bug #3
below.) And it reconciled `mssql_build/README.md`, `DESIGN.md`, and
`README.md`, which still described the Phase-2 Paramiko/SSH architecture and
a placeholder-skeleton build role — code had moved on twice since those docs
were last true.

**Lesson:** when a role gets included from more than one place
(`roles:` in one playbook, `include_role:` in another), check whether Ansible
is resolving the same physical directory both times before assuming a task
edit took effect everywhere it should have.

## Phase 8 — Live-testing the full AG end to end (`d5763a3`, 2026-08-02)

This is the commit that made the AG actually work. Everything up to this
point had passed `ansible-playbook --syntax-check`, which only validates YAML
structure — it can't catch any of the following, because they're all runtime
behavior. Each was found by actually running the workflow against the real
VMs and independently verifying the result with direct `sqlcmd` queries
(not just trusting the playbook's own `debug` output).

**1. Data/backup/log directories were `root:root`.**
`configure.yml` created `data_dir`/`log_dir`/`backup_dir`, but the `mssql`
service account couldn't write to them — `RESTORE DATABASE`/`BACKUP DATABASE`
both failed with OS error 5 (access denied), an error message that doesn't
obviously point at "wrong file ownership."
*Fix:* set `owner: mssql, group: mssql` in `configure.yml`, `backup.yml`, and
`restore.yml`'s directory-creation tasks.

**2. Missing `GO` batch terminator on heredoc `sqlcmd` calls.**
The `BACKUP DATABASE`/`RESTORE DATABASE` heredocs piped into `sqlcmd` had no
`GO` at the end. `sqlcmd` silently accepted the input and executed **nothing**
— exit code 0, no output, no error. The worst kind of failure: everything
*looks* successful.
*Fix:* added `GO` to both heredocs.

**3. `tags: always` on `include_tasks` wasn't actually reliable** for forcing
child-task execution under a `--tags` filter on the Ansible version in use —
Phase 7's fix didn't fully hold. `deployer.py`'s `tags=["adventureworks"]`
fast path for `restore_adventureworks` silently skipped `configure.yml`
entirely, so a restore could run against directories that were never
correctly owned.
*Fix:* dropped tag-based filtering from `restore_adventureworks` and
`_run_full_ag_sequence` — they now run the **full** `site.yml` (optionally
`--limit`ed to a host) instead of trying to cherry-pick tasks by tag.

**4. Failed sub-steps didn't stop the sequence.**
`_run_full_ag_sequence` (the `full-ag` endpoint's implementation) kept calling
the next playbook even after a prior one failed, and the outer task history
always reported `"success"` regardless of any sub-step's real exit code.
*Fix:* added `SequenceStepError` (carries the partial results dict) — a failed
step now stops the sequence and the task history reports `failed` with the
real `stdout`/`stderr` attached. This is the pattern the teardown/rewind work
reuses (see the implementation-plan doc).

**5. Certificate files copied to vm2 were `root:root` mode `0600`.**
Same shape as bug #1 but for the AG certificate relay — unreadable by the
`mssql` service account after `copy`.
*Fix:* set correct ownership on the copy task.

**6. Recovery-model switch needs a fresh full backup first.**
`ALTER DATABASE AdventureWorks SET RECOVERY FULL` was being followed directly
by a log backup, but SQL Server requires a full backup taken *after* switching
into `FULL` recovery before a log backup will succeed — the log chain can't
start from a backup taken under `SIMPLE` recovery.
*Fix:* added a full backup (`aw_full_seed.bak`) immediately before the log
backup (`aw_log_seed.bak`) in `alwayson.yml`.

**7. Two DMV queries referenced columns that don't exist on those views.**
`database_name` isn't a column on `sys.dm_hadr_database_replica_states`, and
`replica_server_name`/`synchronization_state_desc` aren't columns on
`sys.dm_hadr_availability_replica_states` — both queries had been written
from memory rather than checked against the actual DMV schema.
*Fix:* joined to `sys.databases`/`sys.availability_replicas` to get the real
column names.

**8. AG replica identity used the wrong hostname source.**
`CREATE AVAILABILITY GROUP ... REPLICA ON N'vm1'` used the Ansible inventory
hostname, but SQL Server matches replicas by `@@SERVERNAME`
(`devops_VM1`/`devops_VM2` in this lab) — the AG silently failed to recognize
its own replicas under the inventory name.
*Fix:* switched to the `vmware_name` hostvar already defined in
`inventory/hosts.ini`, which matches `@@SERVERNAME`.

**Result, verified independently via direct `sqlcmd` queries (not the
playbook's own output):** `devops_VM1 PRIMARY HEALTHY`,
`devops_VM2 SECONDARY HEALTHY`, `AdventureWorks` `SYNCHRONIZED` on both
replicas.

## Phase 9 — Making the run observable (`68bf1cb`, `86653c9`, both 2026-08-02)

Up through Phase 8's debugging, there was **no persistent Ansible log at
all** — `ansible-playbook` output only existed in the FastAPI process's
in-memory task history (gone on restart) or as terse one-line events in
`app.log`. That makes exactly the kind of debugging Phase 8 required (reading
back what actually happened on a failed run) much harder than it needed to
be.
*Fix:* added `python-fastapi-mssql/ansible.cfg` with `log_path =
./logs/ansible.log`, so every run's full stdout/stderr persists regardless of
process restarts.

Immediately after, `86653c9` corrected a documentation gap that could send
someone chasing SSH connectivity for no reason: `RUNBOOK.md`/`README.md`
implied every log needed an SSH hop to VM1, the same as VM2 — but VM1 is also
the controller running `uvicorn`/`ansible-playbook`, so its own logs
(`ansible.log`, `app.log`, its own SQL Server `errorlog`) are just local
files.

## Phase 10 — Documentation (`a823077`, 2026-08-02)

Added a self-contained architecture/swim-lane diagram of the finished AG
pipeline — a snapshot of the end state after nine phases of real iteration,
not the starting design.

## Lessons learned — quick reference

| Lesson | Where it bit |
|---|---|
| `ansible-playbook` needs a POSIX control node; don't fight a Windows dev box for it | Phase 1 → 2 |
| Deciding *whose* Ansible tree a service points at is an architecture decision, not a detail — decoupling FastAPI's tree from AWX's was deliberate and is why they're divergent today | Phase 2, 4 |
| Nail down real inventory/topology before trusting any playbook run | Phase 3 |
| When a VM is both a deployment target and the controller, it still needs its own `ssh-copy-id` — don't assume the loopback hop is already authorized | Phase 6 |
| A file path that "looks right" (`/home/user/.ssh/id_rsa`) can still be a leftover from a different OS (`/c/Users/...`) — check it was actually updated, not just declared updated | Phase 6 |
| Ansible resolves roles relative to the *playbook's* directory absent a `roles_path` override — a role included from two places can silently fork into two physical copies | Phase 7 |
| `--syntax-check` only validates YAML structure — none of the 8 live-testing bugs in Phase 8 were catchable by it | Phase 8 |
| `tags: always` on `include_tasks` is not a reliable guarantee under `--tags` filtering — prefer running full playbooks (`--limit` if needed) for correctness-critical paths | Phase 7, 8 (bug #3) |
| `sqlcmd` heredocs need an explicit `GO` — without it, exit code 0 and no output can mean nothing ran at all | Phase 8 (bug #2) |
| Directory/file ownership failures (OS error 5) don't announce themselves as ownership problems | Phase 8 (bugs #1, #5) |
| DMV column names should be checked against the actual view, not written from memory | Phase 8 (bug #7) |
| SQL Server AG replica identity is `@@SERVERNAME`, not whatever name your automation tool calls the host | Phase 8 (bug #8) |
| A multi-step orchestration sequence needs to actually stop and report failure on a failed step — "ran to completion" and "succeeded" are different claims | Phase 8 (bug #4) |
| Verify against the system itself (`sqlcmd`, `systemctl`), not just the automation tool's own "success" output | Phase 8 result, repeated in the teardown/rewind plan's verification steps |
| A persistent log that survives process restarts is worth adding *before* the debugging session that needs it, not after | Phase 9 |
| When a host plays two roles (controller + target), say so explicitly in the docs — otherwise "SSH to check the log" gets applied somewhere it doesn't need to | Phase 9 |
