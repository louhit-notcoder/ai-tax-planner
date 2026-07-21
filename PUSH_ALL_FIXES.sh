#!/bin/bash
cd ~/Documents/green-papaya/green-papaya-v3-production
rm -f .git/index.lock
git add .
git status --short
git commit -m "Fix: Prevent infinite loops - better error handling in Dashboard and AuthContext

Changes:
- Dashboard: Added error state display, better loading UX, no more crash on API failure
- AuthContext: Prevent re-setting user on network errors, added debug logging
- api.ts: Hardcoded backend URL fallback, comprehensive debug logging

This fixes the infinite loading/glitching issue."
git push
echo "=========================================="
echo "PUSHED! Now redeploy in Vercel."
echo "=========================================="
