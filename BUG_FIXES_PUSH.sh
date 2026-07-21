#!/bin/bash
# Push all bug fixes to GitHub

cd ~/Documents/green-papaya/green-papaya-v3-production

# Remove lock file if exists
rm -f .git/index.lock

# Stage all changes
git add .

# Check what changed
git status --short

# Commit with descriptive message
git commit -m "Fix: MFA flow loop, client-side validation, error handling

- auth_routes.py: Bootstrap now sets mfa=True (was mfa=False)
- App.tsx: Fixed MFA redirect logic (only redirect if mfa_enabled AND !mfa_verified)
- LoginV3.jsx: Added client-side validation with user-friendly error messages
- AuthContext.tsx: Added mounted ref to prevent memory leaks, better error handling

Fixes:
- Infinite redirect loop on login
- Cryptic validation error messages
- Client-side validation before API calls
- Better error display in forms"

# Push to origin
git push

echo "=========================================="
echo "DONE! Now go to Vercel and Redeploy."
echo "=========================================="
