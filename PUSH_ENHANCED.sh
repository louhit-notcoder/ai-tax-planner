#!/bin/bash
cd ~/Documents/green-papaya/green-papaya-v3-production
rm -f .git/index.lock
git add .
git status --short
echo "Committing enhanced CaseWorkspaceV3 with chat-first UI..."
git commit -m "Enhance CaseWorkspaceV3: Chat-first UI with inline document upload

- Upload button inside chat input area
- Multi-file upload with progress tracking
- Password modal for encrypted PDFs
- Document summaries after processing
- Quick action buttons for common queries
- Enhanced computation panel with regime comparison
- Tax saving indicators and missing info alerts
- Improved document management with filtering"
git push
echo "=========================================="
echo "PUSHED! Steps to test:"
echo "1. Add OpenRouter keys in Render"
echo "2. Redeploy Render"
echo "3. Redeploy Vercel"
echo "4. Sign up / Sign in"
echo "5. Create a client and case"
echo "6. Test the chat with document uploads"
echo "=========================================="
