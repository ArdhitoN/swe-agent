# Notes

Facts about the environment that affect how the experiment runs. Newest first.

## Docker images (2026-11-01)

**Each SWE-bench image is about 4 GB, and images share almost nothing** (117 MB shared,
~4.07 GB unique per image). All 14 chosen bugs would need ~57 GB; this machine has ~17 GB free.

**So we work one bug at a time:** download a bug's image, run everything that needs it,
grade, then delete the image. At most 2–3 images are on disk at once.
- Deleting an image doesn't immediately return space to macOS: Docker Desktop keeps the freed
  space inside its own disk file. That space *is* reused by the next image, so the
  one-at-a-time approach still works.
- Re-downloading an image takes a few minutes. That only costs time, not money.

**This Mac runs the x86 images under emulation.** Docker Desktop 29.9 on an arm64 Mac.
Importing Django inside a container takes under 1 second, so emulation is fast enough.

## Leak checks on the images

Checked so far (full results in `reports/image_checks.json`; every image is checked when it
is first downloaded):

| Bug | Commits after the bug's commit | Internet access |
|---|---|---|
| `django__django-11790` | 0 | yes |
| `django__django-11815` | 0 | yes |

- **Future git history: not present.** `git rev-list --all --not HEAD` finds 0 commits, and there
  are no remotes or stashes. So `git log --all` can't reveal the fix in these images.
  (Older SWE-bench images had this loophole: SWE-bench issue #465.)
- **Internet access: present.** From inside a container, an agent could download a newer version
  of the package that already contains the fix. Our agent blocks network commands. The baseline
  must stay unmodified, so instead we **scan every trajectory of both agents** for network
  commands and report any we find.
