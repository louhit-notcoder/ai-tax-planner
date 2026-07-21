# Render Environment Variables
# Add these in Render Dashboard > Your Service > Environment

## Required Variables (sync: false = click edit to add)

```
GREEN_PAPAYA_ENV=development
DATABASE_URL=postgresql+psycopg://neondb_owner:npg_wFLNsf6dHag9@ep-nameless-recipe-az5z4n7j-pooler.c-3.ap-southeast-1.aws.neon.tech/greenpapaya?sslmode=require&channel_binding=require
JWT_SECRET=change-this-to-a-random-secret-at-least-48-characters-long
APP_BASE_URL=https://your-vercel-url.vercel.app
CORS_ALLOWED_ORIGINS=https://your-vercel-url.vercel.app
ENCRYPTION_KEY_HEX=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
BLIND_INDEX_SECRET=change-this-blind-index-secret
STORAGE_BACKEND=local
LOCAL_STORAGE_ROOT=/tmp/storage
MAX_UPLOAD_BYTES=52428800
ALLOW_DEV_BOOTSTRAP=true
DEV_BOOTSTRAP_EMAIL=owner@greenpapaya.local
DEV_BOOTSTRAP_PASSWORD=V3Dev-Password-123!
MALWARE_SCAN_REQUIRED=false
REQUIRE_MFA_FOR_PRIVILEGED_ROLES=false
```

## Optional Variables (AI features)

```
OPENROUTER_API_KEY=sk-or-replace-with-your-key
OPENROUTER_ASSISTANT_MODEL=anthropic/claude-sonnet-4-20250514
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```
