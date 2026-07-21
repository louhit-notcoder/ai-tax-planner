#!/bin/bash
# Push the fix to GitHub

cd ~/Documents/green-papaya/green-papaya-v3-production

# Remove lock if exists
rm -f .git/index.lock 2>/dev/null

# Add, commit, push
git add .
git commit -m "Fix: Add npm overrides for React 18 types"
git push

echo "Done!"
