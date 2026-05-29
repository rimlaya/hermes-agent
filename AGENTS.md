# Hermes Agent - Agent Instructions

Keep this file small. It is loaded into agent context and should contain only
rules that must be visible before touching the repository.

## Safety Gates

- Before changing files that affect the multi-agent system, Discord gateways,
  launchd services, tokens, auth files, cross-agent handoffs, agent memory, or
  operating-model prompts, run Maestro intake from `/Users/miyaihisataka/Vault`.
- Do not expose token values, auth JSON, keychain material, or `.env` contents
  in notes, logs, command output summaries, or chat responses.
- Treat live gateway switches, launchd changes, service restarts, destructive
  operations, secrets/auth changes, and production-impacting changes as gated:
  verify current processes first, document rollback, and get explicit user GO
  before mutating.
- Avoid starting a second live process that may reuse the same platform token.

## Local Checks

- Maestro status: `cd /Users/miyaihisataka/Vault && maestro status`
- Maestro tasks: `cd /Users/miyaihisataka/Vault && maestro task list`
- Provider health: `cd /Users/miyaihisataka/Vault && maestro providers doctor`

For implementation details, inspect the current filesystem and nearby source
files instead of relying on a long always-loaded guide.
