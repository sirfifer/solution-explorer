---
name: repo-story
description: Work out which version of a codebase to actually analyse. Run once per new subject, before the first fetch, to decide policy.follow in demos/registry/<slug>.json. Every repo has its own story about what "working" means, and getting it wrong means demoing something broken.
---

# /repo-story - which version of this codebase should we show?

Run this **once per new subject, before the first fetch.** Its output is the
`policy` block in `demos/registry/<slug>.json` plus a written record of why.

## Why this exists

"Pull the latest" is a guess that happens to be right some of the time.

For a project like reference editor repository it is probably fine: `main` is heavily protected,
nothing lands without CI and review, and HEAD is close to a release candidate.
For a project whose `main` is a working branch, HEAD can be broken for days at a
stretch, and the only version anyone stands behind is a tag or the last green
pipeline.

We are building something to **show people**. A map of a broken commit is worse
than useless: it is a confident, detailed picture of something that does not
work, and every oddity in it invites the question "is that the code or is that
your tool?" The goal is the most recent version that is also **healthy and fully
functional**, and only the repo can say where that is.

Sometimes the answer is written down. Projects do say things like "do not build
from master, use the release branch". If a repo tells us how to get a working
copy and we ignore it, that is entirely our fault.

## What to produce

A decision, its evidence, and a way to check it later.

```json
"policy": {
  "follow": "default-branch" | "latest-tag" | "pinned",
  "pin": null,
  "exclude": [],
  "history": "full"
}
```

Plus `docs/publication/repo-stories/<slug>.md` recording:

- **The verdict** and the one sentence that justifies it.
- **The evidence**, quoted, with URLs. Not "the docs suggest"; the actual line.
- **The expected signature** of a healthy fetch: what the resolved ref should
  look like, so a later run can check it blind (see Tuning).
- **What would change this**, so a re-run knows what to look at.

## The investigation

Work down this list. Stop when the answer is decisive; record what settled it.

**0. Note that a wrong answer here is silent.** Every step below produces a ref
that will clone successfully and analyse cleanly whether or not it is the right
one. Nothing downstream will complain. That is why the proof step exists and why
this is worth doing carefully rather than quickly.

**1. Ask the project directly.** README, CONTRIBUTING, RELEASE, and any
`docs/` build instructions. Search for `stable`, `release`, `do not build`,
`unstable`, `nightly`, `development branch`. An explicit instruction outranks
every inference below it.

**2. What is the default branch, and is it protected?**
`git ls-remote --symref <repo> HEAD` names it. Then ask whether landing there is
gated: required checks, review rules, a merge queue. A gated default branch is
usually safe to follow. An ungated one is a working surface.

**3. Does CI certify commits, and can we see which?** A repo with a green-build
badge or published pipeline results can tell us the last commit that passed. If
the project publishes that, following the last green commit beats following HEAD
by a wide margin and costs one API call to resolve.

**4. Are there releases, and how recent?** `git ls-remote --tags`. Weigh two
things against each other:
   - a tag is a version someone deliberately stood behind
   - a tag six months stale shows a codebase nobody will recognise

   Recent, regular tags are the strongest signal available. Rare or ancient tags
   mean the project's real cadence lives on a branch.

**5. Release branches.** Some projects keep `release/*` or `stable` as the
thing that works while `main` churns. If one exists and tracks close to HEAD,
it is usually the best answer: current AND vouched for.

**6. What does the history look like?** Commit frequency on the default branch,
and whether reverts and "fix the build" commits are common. Frequent build
fixes on the default branch mean HEAD is often broken, whatever the docs claim.

## Choosing

| Evidence | `follow` |
|---|---|
| Docs name a branch to build from | `pinned` to that branch, or `default-branch` if it IS the default |
| Default branch gated by required CI and review, tags rare | `default-branch` |
| Regular recent releases, default branch churns | `latest-tag` |
| Docs warn against the default branch | never `default-branch` |
| Anything ambiguous | `pinned` to a commit you verified by hand, and say so |

When two options are defensible, prefer the one that is **more recent** as long
as its health evidence is real. Showing a stale codebase is its own failure: it
invites "this is not what our repo looks like", which is the same credibility
loss by a different route.

## Prove it before recording it

A verdict that has not been executed is a hypothesis. Run these four checks and
paste the output into the story file. They cost seconds and they are the
difference between "this looks right" and "this works".

    # 1. our own resolver returns what you expect
    python3 -c "...resolve_ref(repo, {'follow': ..., 'pin': ...})"

    # 2. the ref exists, and note whether the tag is lightweight or annotated.
    #    An annotated tag has a second ^{} line; the commit is the ^{} one, and
    #    tooling that grabs the first line gets a tag object instead of a commit.
    git ls-remote --tags <repo> | grep -E "refs/tags/<ref>(\^\{\})?$"

    # 3. it actually clones at that ref
    git clone --depth 1 --branch <ref> <repo> /tmp/pinprobe

    # 4. ancestry and recency, which decide whether the choice is still current
    git merge-base --is-ancestor <sha> origin/main   # is it on the main line?
    git log -1 --format=%ci <sha>                    # how old is it?
    git rev-list --count <sha>..origin/main          # how far behind?

**Recency is part of the verdict, not a footnote.** A release tag six days old
with the default branch 341 commits ahead is an excellent choice. The same tag
six months old is a different decision entirely, and the only way to tell is to
ask. If the chosen ref is more than a release cycle behind, say so explicitly and
justify it, or choose again.

**If a check fails, the verdict is wrong, not the check.** Go back to the
investigation with what the failure taught you.

## Tuning, which is the point of writing it down

This skill will be wrong sometimes. The value is that being wrong is cheap to
fix and the fix is permanent.

When a subject turns out to have been fetched at a bad ref:

1. **Root-cause it to a step above.** Which signal was missed, or read wrongly?
   There is almost always a signal; the question is why this procedure walked
   past it.
2. **Change the procedure so it would have produced the right answer.** Not the
   registry entry. Anyone can fix one registry entry; the point is that the next
   subject gets the benefit.
3. **Re-run blind and check.** The right answer is now known, so run this skill
   against that repo from scratch, with no memory of the outcome, and see
   whether it lands there. This is why every record carries an expected
   signature: it makes the check mechanical rather than a matter of opinion.
4. **Repeat until it lands.** These are small edits. A few rounds across a few
   subjects should be enough for a long while.

Record each tuning round in the subject's story file, because the next person to
disagree with this procedure deserves to know what it already learned.

## Cost

Nothing but a few `git ls-remote` calls and some reading, which is why it runs
before the first fetch rather than after something goes wrong. It is the cheapest
step in the whole pipeline and it decides what every later step is looking at.
