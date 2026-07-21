#!/bin/bash
cd ~/Documents/green-papaya/green-papaya-v3-production
rm -f .git/index.lock 2>/dev/null
git add .
git commit -m "Fix: MFA flow loop - bootstrap sets mfa=True, App.tsx logic fixed"
git push
echo "Done! Now redeploy in Vercel."
