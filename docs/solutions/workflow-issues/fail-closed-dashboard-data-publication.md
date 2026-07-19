---
title: "Fail-Closed Dashboard Data Publication"
date: 2026-07-20
category: workflow-issues
module: dashboard-publication
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "A local workflow downloads data, derives analysis artifacts, and publishes them through Git."
  - "A generated dashboard snapshot must remain traceable to one exact source archive."
  - "Automation pushes directly to a deployment branch such as main."
tags:
  - "dashboard-publication"
  - "fail-closed"
  - "git-safety"
  - "snapshot-provenance"
  - "atomic-publish"
  - "powershell"
---

# Fail-Closed Dashboard Data Publication

## Context

A dashboard refresh that downloads a production export, runs local analysis, replaces a public
snapshot, commits, and pushes is a release transaction. A clean Git worktree alone does not make
that transaction safe: it can be on the wrong branch, contain clean but unpublished history, move
during a long analysis, or publish a different timestamped ZIP than the downloader just created.

The first publisher draft checked cleanliness only, rescanned the export directory for the newest
filename, checked repository state only at startup, used an unscoped commit, and attempted rollback
without verifying its result. Source-text tests proved that commands appeared in the script but not
that Git history, rollback, or remote publication behaved correctly.

## Guidance

Treat source identity, Git history, mutation scope, and failure phase as explicit invariants.

1. Fetch the deployment branch and require the local branch name and `HEAD` to exactly equal the
   fetched remote tip. Reject detached HEAD and merge, rebase, cherry-pick, or revert state.
2. Consume the exact ZIP path returned by the downloader. Do not infer the release by rescanning
   timestamps or filenames.
3. Bind analysis to that ZIP through a completed manifest whose `source_archive` and
   `source_sha256` match the file being published.
4. Assemble the complete public bundle outside the repository, then recheck `HEAD` and the full
   tracked/untracked status after analysis and before mutating public files.
5. Stage only the publication directory. Reject staged paths outside it, unstaged changes, and
   untracked files. Record the validated index tree with `git write-tree`, commit that index, and
   verify the commit parent, tree, and changed paths before pushing.
6. Before a commit exists, restore only the publisher-owned directory and verify rollback command
   exit codes plus a clean owned path. After a valid commit exists, preserve it when push fails and
   report the exact hash-based retry command.

Push the verified commit hash to the full remote ref instead of pushing a symbolic local branch:

```powershell
$pushRef = "${publishedHead}:refs/heads/$Branch"
git push $Remote $pushRef
```

This guarantees that the object inspected after commit is the object offered to the deployment
branch. A remote race remains fail-closed because a non-fast-forward push is rejected.

## Why This Matters

A wrong archive or mixed commit can still render a plausible dashboard. Provenance errors are
therefore more dangerous than an obvious crash: viewers may trust an analysis whose source and
history cannot be reproduced.

Exact remote-baseline equality gives the generated data commit one known parent. Manifest digest
binding connects derived analysis to one immutable Export Release. A second repository check closes
the concurrency window created by analysis. Index-tree and post-commit validation ensure the pushed
commit contains the exact staged snapshot rather than later working-tree content. Verified rollback
distinguishes an attempted cleanup from a restored public state.

## When to Apply

- Generated reports or dashboards are committed and pushed automatically.
- A local step derives artifacts from an immutable remote export.
- Analysis is long enough for another editor, process, or agent to change the repository.
- Multiple timestamped artifacts coexist and only the current invocation owns one of them.
- Network delivery can fail after a valid local publication commit is created.

## Examples

Behavioral tests should use real temporary repositories and bare remotes rather than only mocking
Git command text. The publisher suite covers:

- a misleading future-dated ZIP while the downloader returns an older-named current release;
- a clean local branch one commit ahead of the remote;
- a concurrent staged file created during analysis;
- a manifest SHA mismatch before public mutation;
- a failing pre-commit hook followed by verified snapshot restoration; and
- a deleted test remote that causes push failure while preserving the scoped local commit.

The durable test assertion is repository state, not console output alone:

```python
assert rev_parse(repository, "HEAD^") == baseline
assert rev_parse(repository, "origin/main") == rev_parse(repository, "HEAD")
assert all(path.startswith("portfolio_data/") for path in committed_paths)
```

## Related

- [Harden the Production CSV Exporter Integration Contract](../integration-issues/production-csv-exporter-integration-contract.md)
- [Validate the Export Dashboard Contract and Empty States](../integration-issues/validate-export-dashboard-contract-and-empty-states.md)
- [Snapshot-Driven, Replayable Monitoring Pipeline](../architecture-patterns/snapshot-driven-replayable-monitoring-pipeline.md)
