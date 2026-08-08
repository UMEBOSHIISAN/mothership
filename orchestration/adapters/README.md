# Local adapter boundary

`orchestration.lib.adapters` builds immutable adapter plans for the fixed public
aliases `claude-code-agent`, `codex-cli`, and `ollama-local`. It does not launch
them. Plans carry a sanitized child environment, the locked staged-context
working directory, and either the prompt bytes or a binary-safe context envelope.

`build_adapter_plan_preview` only validates the prospective `staged-context`
path used by a later dry-run. It never creates the stage or reads prompt/context
files.

`orchestration/bin/llm-doctor` is a diagnostic surface, not an executor. It
performs only a version command plus one help/list command for each requested
adapter, in a sanitized environment and with `/` as its working directory. It
never invokes a model, installs software, authenticates, or modifies settings.
`bootstrap/doctor.sh` resolves the packaged diagnostic executable and performs
one `exec` with its original arguments.
