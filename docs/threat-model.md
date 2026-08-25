# Threat model and tool fit

envskill is a local, least-privilege delivery tool. It helps a coding agent pass
only the credential names needed by one command, without putting values in a
prompt, skill file, repository, shell history, or a broad child environment.
It is not a hosted secret manager, an encryption layer, or an operating-system
sandbox.

## Boundary: `run --only`

`envskill run --only NAME1,NAME2 -- command` starts `command` with a minimal
functional environment, the selected store values, and any non-secret parent
variables explicitly named with `--inherit`. Other stored variables are not
injected. `--all` deliberately removes that least-privilege boundary and should
be an explicit exception.

This boundary ends at the receiving process. A child process can read every
secret injected into its own environment and can log, transmit, persist, or
otherwise exfiltrate it. envskill cannot make an untrusted command safe, stop
same-user code from reading the local store, or contain subprocesses launched
by a receiving command.

## Local-store protections

On POSIX systems, envskill requires the store to be a regular, current-user
owned `0600` file in a real, current-user-owned parent directory that is not
group- or world-writable. It rejects symlinked stores, non-regular files,
foreign-owned stores, and unsafe permissions.

Writes take a per-store kernel lock, write a temporary `0600` file in the same
directory, then atomically replace the store. `envskill set` is therefore also
the rotation path: the next `envskill run` reads the current value without an
agent restart. These controls reduce accidental disclosure and common local
file-handling mistakes; they do not encrypt a value at rest or protect it from
the same operating-system user.

## Choosing complementary tools

| Tool | Primary job | Where envskill fits |
| --- | --- | --- |
| `.env` | Keep local configuration in a file. | Move selected values to the private store, then inject only what one command needs. |
| direnv | Automatically load a directory's environment into a shell. | Use envskill when automatic broad shell injection is too much access. |
| 1Password, Doppler, Infisical | Govern, share, audit, and distribute secrets. | Fetch or sync an approved local value, then narrowly deliver it to an agent command. |
| OS/container sandbox | Restrict filesystem, processes, network, and other runtime capabilities. | Combine it with envskill to limit what a command receives and what it can do with it. |

For higher-risk commands, prefer short-lived credentials, provider-side scopes
limited to the exact API/project/action, and separate credentials per workload.
Pair those controls with a sandbox that limits network egress and filesystem
access. Revoke or rotate a credential after suspected disclosure; envskill does
not detect or undo an exfiltration.
