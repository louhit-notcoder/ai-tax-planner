#!/bin/bash
cd ~/Documents/green-papaya/green-papaya-v3-production
rm -f .git/index.lock
git add .
git commit -m "Debug: Add console logs to api.ts to trace network error"
git push
echo "Pushed! Now redeploy in Vercel."
