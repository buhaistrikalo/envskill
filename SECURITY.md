# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose credential values. Use GitHub's private vulnerability reporting for this repository.

Include the affected version, operating system, reproduction steps, and whether secret material reached stdout, stderr, process arguments, logs, or another process.

## Scope

envskill protects against accidental disclosure and unnecessarily broad environment injection. It does not isolate processes running as the same operating-system user. Any process receiving a credential can read it, and an unrestricted process may read the backing file directly.
