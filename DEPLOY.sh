#!/bin/bash
# Green Papaya V3 - Deploy Script
# Run this in Terminal from the green-papaya-v3-production folder

set -e

echo "🚀 Green Papaya V3 - Deploy Setup"
echo "=================================="

cd ~/Documents/green-papaya/green-papaya-v3-production

# Initialize git if not exists
if [ ! -d ".git" ]; then
    echo "📦 Initializing git..."
    git init
fi

# Add all files
echo "📝 Adding files..."
git add .

# Commit
echo "💾 Committing..."
git commit -m "Green Papaya V3 - Production deployment"

# Add remote (replace YOUR_GITHUB_USERNAME if needed)
echo "🔗 Connecting to GitHub..."
git remote add origin https://github.com/louhit-notcoder/ai-tax-planner.git 2>/dev/null || git remote set-url origin https://github.com/louhit-notcoder/ai-tax-planner.git

# Push
echo "📤 Pushing to GitHub..."
git branch -M main
git push -u origin main --force

echo ""
echo "✅ Code pushed to GitHub!"
echo ""
echo "Next steps:"
echo "1. Go to https://render.com and create a Web Service"
echo "2. Connect to your GitHub repo"
echo "3. Set Root Directory to 'backend'"
echo "4. Add environment variables (see RENDER_ENV_VARS below)"
echo ""
