---
description: Run the Opus phase-gate review for the current (or named) phase before proceeding.
argument-hint: "[phase number or name]"
model: opus
---

Run a phase-gate review for phase: $ARGUMENTS

Delegate to the `phase-gate-reviewer` subagent. If no phase is given, infer the current phase from
recent work and `CLAUDE.md`. Produce a GO / NO-GO against that phase's "Done when" criteria, with
specifics. Do not proceed past the gate on a NO-GO.
