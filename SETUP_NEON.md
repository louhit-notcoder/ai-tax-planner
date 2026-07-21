# Green Papaya V3 - Neon Setup Guide

## Step 1: Create Neon Account (2 minutes)

1. **Go to:** https://neon.tech
2. **Click:** "Sign up" → Use GitHub or email
3. **No credit card required** for free tier

---

## Step 2: Create a New Neon Project

1. Click **"New Project"**
2. Fill in:
   - **Project name:** `green-papaya`
   - **Database name:** `greenpapaya`
   - **Region:** Choose closest to you (e.g., `US East (N. Virginia)` or `Asia Pacific (Singapore)`)
3. Click **"Create Project"**

---

## Step 3: Copy Your Connection String

1. You'll see a connection string like:
   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/greenpapaya?sslmode=require
   ```
2. **Copy it** (you'll paste it in Step 4)

---

## Step 4: Update Your .env File

1. Open the file: `green-papaya-v3-production/.env`
2. Replace this line:
   ```
   DATABASE_URL=postgresql://your-neon-username:your-neon-password@ep-xxx.region.aws.neon.tech/greenpapaya?sslmode=require
   ```
   With your actual connection string from Step 3

---

## Step 5: Install Backend Dependencies

Open a new Terminal and run:

```bash
cd green-papaya-v3-production/backend

# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install dependencies
pip install -r requirements-production.txt
```

---

## Step 6: Run Database Migrations

```bash
# Set database URL (or it will read from .env)
export DATABASE_URL="postgresql://user:pass@ep-xxx.region.aws.neon.tech/greenpapaya?sslmode=require"

# Run migrations to create all tables
cd backend && alembic upgrade head
```

**You should see:** `Running migration 0001 ... OK`

---

## Step 7: Start the Backend

```bash
# In the backend directory (with .venv activated)
uvicorn main:app --reload --port 8000
```

**You'll see:**
```
Uvicorn running on http://127.0.0.1:8000
```

**Keep this terminal open!**

---

## Step 8: Start the Frontend

Open a **new terminal window**:

```bash
cd green-papaya-v3-production/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

**You'll see:**
```
VITE v5.x.x ready in xxx ms
➜  Local: http://localhost:5173/
➜  Network: http://192.168.x.x:5173/
```

---

## Step 9: Open the App!

1. **Backend API:** http://localhost:8000/docs
   - This is the Swagger UI where you can test all API endpoints

2. **Frontend:** http://localhost:5173/
   - This is the Green Papaya UI

3. **Login with bootstrap credentials:**
   - Email: `owner@greenpapaya.local`
   - Password: `V3Dev-Password-123!`

---

## Quick Reference

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000/docs |
| Login | owner@greenpapaya.local / V3Dev-Password-123! |

---

## Troubleshooting

### "Module not found" errors
```bash
# Make sure you're in the .venv
source backend/.venv/bin/activate
pip install -r backend/requirements-production.txt
```

### "Connection refused" errors
- Check Neon console: https://console.neon.tech
- Make sure your IP is allowed (Neon allows all by default on free tier)

### "alembic: command not found"
```bash
source backend/.venv/bin/activate
python -m alembic upgrade head
```

---

## What's Next?

Once V3 is running:
1. Create a test client
2. Upload a sample Form 16
3. Test the AI assistant
4. Run the computation

Let me know when you've created the Neon account and I'll help with the next steps!
