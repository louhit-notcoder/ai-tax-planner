# Green Papaya V3 - Local Development

## Quick Start (Neon PostgreSQL - No Installation Required)

This guide walks you through running V3 locally using Neon cloud PostgreSQL.

### Prerequisites
- Node.js (already installed)
- Python 3.9+ (already installed)
- Neon account (free)

---

## Step 1: Create Neon Account (2 minutes)

1. **Go to:** https://neon.tech
2. **Sign up:** Use GitHub or email (no credit card)

---

## Step 2: Create a New Project

1. Click **"New Project"**
2. Settings:
   - **Project name:** `green-papaya`
   - **Database name:** `greenpapaya`
   - **Region:** Closest to you

3. Copy the **Connection string** shown

---

## Step 3: Update .env

Edit `green-papaya-v3-production/.env`:

```bash
# Replace this line with your Neon connection string:
DATABASE_URL=postgresql://user:pass@ep-xxx.region.neon.tech/greenpapaya?sslmode=require
```

---

## Step 4: Install Backend

```bash
cd green-papaya-v3-production/backend

# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install -r requirements-production.txt
```

---

## Step 5: Run Migrations

```bash
# Run database migrations (creates all 33 tables)
cd backend && alembic upgrade head
```

**Expected output:** `Running migration 0001 ... OK`

---

## Step 6: Start Backend

```bash
# Keep this terminal open
uvicorn main:app --reload --port 8000
```

**You'll see:** `Uvicorn running on http://127.0.0.1:8000`

---

## Step 7: Start Frontend (New Terminal)

```bash
cd green-papaya-v3-production/frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

---

## Step 8: Open in Browser

- **Frontend:** http://localhost:3004
- **API Docs:** http://localhost:8000/docs

---

## First Login

1. Go to http://localhost:3004
2. Use the dev bootstrap credentials from `.env`:
   - **Email:** `owner@greenpapaya.local`
   - **Password:** `V3Dev-Password-123!`

---

## Troubleshooting

### "Module not found" errors
```bash
# Make sure you're in the .venv
source .venv/bin/activate
pip install -r requirements-production.txt
```

### "Connection refused" to Neon
```bash
# Verify your DATABASE_URL is correct
# Make sure you added ?sslmode=require
```

### Frontend port already in use
```bash
# Change port in frontend/.env or kill the process
lsof -ti:3004 | xargs kill
```

---

## What's Running

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React)              http://localhost:3004      │
│  Backend (FastAPI)             http://localhost:8000      │
│  PostgreSQL (Neon Cloud)       ep-xxx.neon.tech:5432      │
└─────────────────────────────────────────────────────────────┘
```

---

## Stopping

- **Backend:** Press `Ctrl+C` in that terminal
- **Frontend:** Press `Ctrl+C` in that terminal

Restart with same commands when you return.

---

## Need Help?

1. Check the docs: `docs/LOCAL_SETUP.md`
2. Check API docs: http://localhost:8000/docs
3. Review errors in terminal output
