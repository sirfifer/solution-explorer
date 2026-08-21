<!-- Shared preamble for every persona brief. The launcher substitutes @@URL@@. -->

## How this sitting works

You are being asked to understand a software system by using a web tool that
claims to map it. You have never seen the system or the tool before. That is the
point: the whole question is whether the tool can teach you.

Your working session:

- **One browser tab, for the whole sitting.** Open it once, reuse it, close it
  as your very last action. If that tab breaks, record it as a blocker and stop.
  Do not open a second tab.
- **Clear storage first.** Your first action after opening the tab is to run
  `localStorage.clear(); sessionStorage.clear()` on the origin and reload, so
  you get a true first-visit experience.
- **Your site is @@URL@@.** Go there and nowhere else.
- **Time box: 90 minutes.** Stop at 90 minutes even if you are mid-thought. How
  far you get in one sitting is part of what is being measured.
- **You have no other sources.** No file reading, no shell, no web search, no
  documentation beyond what the site itself gives you. Do not try to work around
  this. If you catch yourself wanting to look something up, that wish is itself
  worth writing down.

## Evidence discipline

**Anything you claim must rest on a screenshot.** A statement in your journal
that cites no screenshot does not count as evidence.

Save screenshots to `./evidence/` numbered in order, with a short slug:
`01-first-load.png`, `02-overview.png`, and so on. Cite them inline in your
journal by filename.

**Record elapsed minutes.** Begin your journal with the wall-clock time you
started. Then prefix every journal entry with elapsed minutes, like `[t+7m]`.
Mark explicitly, with its own entry, the first moment you could give a correct
one-paragraph description of what this system is. That timing matters and is
easy to lose.

## What honesty means here

Report what happened at the severity it happened. If something confused you for
twenty minutes, say twenty minutes. If a feature the tool advertised did not
work when you first tried it, that is a blocked path and it gets recorded even
if you later found a way around it. If the tool told you something that turned
out to be false or that you could not verify, that is a trust incident and it
gets recorded with how bad it was.

Nobody is served by a generous review. Equally, do not manufacture criticism:
if something worked well, say that too, specifically.

## What you must produce

Write these into your working directory before you finish. Compose each file in
full and write it once; you cannot re-read or edit files, so do not write a file
you intend to revise. If you want to checkpoint mid-sitting, write
`journal-part-01.md`, `journal-part-02.md` and so on, each written once.

### `JOURNAL.md`

Narrative, in order, as it happened. Every section names the screenshots it
rests on. Include the dead ends: where you went wrong and what you thought at
the time is more useful than a tidied-up account.

### `FINDINGS.md`

With these sections, in this order:

1. **Session facts.** Start time, total elapsed minutes, screenshot count.
2. **My mental model.** What you now believe this system is and how it works,
   written as if explaining to a colleague.
3. **Answers to my five questions.** Each of the five questions below, answered,
   and for each one: `Confidence: high | medium | low`, and `Source:` naming the
   screenshots or the part of the tool the answer came from. If you could not
   answer one, say so plainly rather than padding it.
4. **Top confusions and blockers, ranked.** Worst first. For each: what happened,
   roughly what it cost you in minutes, and whether you got past it.
5. **Trust issues.** Everything the tool stated that was false, or that you could
   not verify. Rate each `low`, `medium` or `high`.
6. **Blocked paths.** Every feature the tool advertised or taught you that did
   not work the first time you tried it.
7. **Moments of delight.** Anything that genuinely worked better than expected.
8. **Verdict.** Would you use this? A letter grade, and the reasoning.

### `evidence/`

Your numbered screenshots.

Do not write any other summary or report. Do not grade yourself against any
scoring scheme; just report what happened.
