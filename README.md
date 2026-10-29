---
published: false
---

# atlaswealth-main

The site published from this branch is a single contact page.

The previous site is on `full-site-backup`. Merging that branch does nothing once this page is on `main`, because the backup commit is already an ancestor. Replace the published tree with the backup, then commit:

```bash
git checkout main
git pull origin main
git rm -qr .
git checkout full-site-backup -- .
git commit -m "Restore the full site from full-site-backup"
git push origin main
```

The portfolio update workflow on this branch has no schedule and does not write figures. Restoring `full-site-backup` brings the previous workflow back.
