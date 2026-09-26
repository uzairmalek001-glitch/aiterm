AITerm V2 — a reasoning terminal

AITerm is a code-aware terminal with a real interactive shell (PTY) and a background monitoring pipeline that turns failures into structured, evidence-backed diagnostics.

AI is an optional reasoning/enrichment layer — never the detector, never required, and never a single point of failure.

V2 architecture

Terminal / Watcher / Tests / Analyzers
                ↓
         Evidence Collector
                ↓
             Parser
                ↓
       Failure Classifier
                ↓
      Project Context Resolver
                ↓
        Deterministic Diagnosis
                ↓
        ┌───────┴───────┐
        ↓               ↓
   Local reasoning   Optional AI
        ↓               ↓
        └───────┬───────┘
                ↓
             Diagnosis
                ↓
        Fix / Verification
                ↓
          History / Memory

The core design principle is:

«Evidence ≠ Hypothesis ≠ Conclusion»

AITerm first works from observable tool output. AI can enrich the result later, but deterministic detection and initial diagnosis continue to work without an AI backend.

V2 milestone

AITerm V2 can now turn application-level command failures into structured diagnostics.

Added in V2

Command-result bridge

- Captures command output together with exit codes.
- Handles failures even when the application does not emit a standard traceback.

Source-location extraction

- Extracts paths and line numbers from application output.
- Supports formats such as "file.py:10" and contextual "at line 10" messages.

Deterministic failure classification

Currently recognizes:

- Configuration errors
- Syntax errors
- Type errors
- Import errors
- Dependency errors
- Runtime errors
- Test failures
- Compilation errors
- Unknown failures when evidence is insufficient

Evidence-based diagnosis

Produces:

- Category
- Cause
- Confidence
- Supporting evidence
- Verification guidance

VisionTrack integration

AITerm V2 has been tested against real VisionTrack application-level failures.

VisionTrack configuration errors can be captured, located, classified, and diagnosed by AITerm.

Regression coverage

Classifier and diagnosis layers have dedicated tests.

Current regression suite: 128 tests passing.

Example: VisionTrack

Given a VisionTrack command:

aiterm run -- visiontrack inspect-config config/bad.yaml

VisionTrack reports:

Invalid configuration: config/bad.yaml:
invalid YAML at line 3, column 1:
expected ',' or ']', but got '<stream end>'

AITerm extracts the relevant evidence:

Category: CONFIGURATION_ERROR
File: config/bad.yaml
Line: 3

And produces a deterministic diagnosis:

Cause: malformed YAML configuration
Confidence: high

Evidence:
- invalid YAML
- parser expected a closing bracket
- parser expected a comma
- parser reported an error at line 3

Verification:
Inspect config/bad.yaml around line 3 and validate the configuration syntax.

No AI model is required for this initial reasoning.

AI can subsequently provide optional deeper analysis when enabled.

Install

pip install -e .

Optional watcher support:

pip install -e ".[watch]"

Development dependencies:

pip install -e ".[dev]"

Check the local environment:

aiterm doctor

Quick start with Gemini

AI is disabled until explicitly enabled.

export GEMINI_API_KEY=...
aiterm config --init

Then configure the AI provider in "aiterm.toml":

[ai]
enabled = true
provider = "gemini"
model = "<your model id>"

Check the configuration:

aiterm doctor

Run AI-assisted analysis:

aiterm analyze --ai

Or explain an existing diagnostic:

aiterm explain <id>

AI calls run on a background worker. The deterministic/local notification is delivered first, followed by optional AI enrichment.

Use

Command| What it does
"aiterm" / "aiterm start"| Interactive shell in a PTY with live monitoring
"aiterm watch"| Monitoring only; prints notification boxes
"aiterm analyze [path]"| One-shot project/file analysis
"aiterm analyze [path] --json"| Machine-readable analysis
"aiterm analyze [path] --ai"| Analysis with optional AI enrichment
"aiterm run -- <cmd>"| Run a command and analyze its output
"aiterm history"| Show recent problems and their IDs
"aiterm explain <id>"| Explain a diagnostic
"aiterm fix <id>"| Show a proposed fix and require explicit approval
"aiterm config"| Show effective configuration
"aiterm config --init"| Create "aiterm.toml"
"aiterm doctor"| Check available tools, watchers, notifications, and AI configuration

Deterministic vs AI

Deterministic layer

The following remain locally derived from observable evidence:

- File
- Line
- Column
- Severity
- Category
- Message
- Fingerprint
- Diagnostic identity
- Initial diagnosis
- Verification guidance

AI layer

AI output is explicitly separated as inference.

For example:

AI analysis (inference, confidence 95%)
...
(manual review recommended)

AI does not become the source of truth for the original diagnostic.

Supported languages

Current analyzers include:

- Python
- JavaScript
- TypeScript
- C
- C++
- Java
- Kotlin
- Rust

A missing compiler or toolchain disables the corresponding analyzer rather than preventing AITerm from operating.

Add a language by implementing a "LanguageAnalyzer" and registering it with the analyzer system.

Tests

Run the complete test suite:

pytest -q

Current V2 regression baseline:

128 tests passed

Coverage includes monitoring, debouncing, parsers, redaction, AI context, providers, outages, patches, history recovery, command-result handling, deterministic classification, deterministic diagnosis, and end-to-end failure scenarios.

Security and privacy

AITerm follows a local-first architecture.

- AI is optional.
- API keys are read from the environment.
- AI context is redacted before external calls.
- Deterministic diagnostics do not require network access.
- Proposed patches require explicit approval.
- AI output is treated as inference rather than verified fact.

Current V2 direction

The current milestone establishes the deterministic reasoning foundation.

Next development areas include:

Deterministic diagnosis
        ↓
Project context
        ↓
Cross-file reasoning
        ↓
Fix proposals
        ↓
Verification
        ↓
History / memory
        ↓
Failure recognition across time

The long-term goal is a terminal that can observe a failure, understand the project context, reason about the evidence, propose a fix, and verify whether the fix actually worked.