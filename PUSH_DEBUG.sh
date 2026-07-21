#!/bin/bash
cd ~/Documents/green-papaya/green-papaya-v3-production
rm -f .git/index.lock
git add .
git commit -m "Fix: Hardcode backend URL as fallback + debug logging"
git push
echo "Pushed! Now redeploy in Vercel."
