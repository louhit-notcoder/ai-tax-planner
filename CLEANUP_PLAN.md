# Cleanup Plan - Keep Only V3

## ⚠️ PREREQUISITE: Docker Desktop Required

Install Docker Desktop before running V3:
1. Download from: https://www.docker.com/products/docker-desktop/
2. Start Docker Desktop
3. Verify: `docker --version`

---

## Files/Directories to DELETE (V1/V2)

These are superseded by V3:

```
/green-papaya/                      # Current directory
├── backend/                    # DELETE - V1 backend, superseded
├── frontend/                  # DELETE - V1 frontend, superseded  
├── memory/PRD.md              # DELETE - old PRD, superseded
├── test_data/                # DELETE - old test data
├── test_reports/             # DELETE - old test reports
├── tests/                    # DELETE - old tests
├── auth_testing.md           # DELETE - obsolete
├── test_result.md            # DELETE - obsolete
├── README.md                 # DELETE - obsolete
├── green-papaya-v2-build-report.md  # DELETE - obsolete
├── green-papaya-v2-production-foundation/  # DELETE - superseded
└── green-papaya-v3-build-report.md       # KEEP - V3 reference
```

## Files/Directories to KEEP (V3)

```
/green-papaya/
└── green-papaya-v3-production/   # MAIN PROJECT
    ├── backend/                  # ✅ Production backend
    ├── frontend/                 # ✅ Production frontend
    ├── docs/                     # ✅ Documentation
    ├── memory/                   # ✅ Memory files
    ├── scripts/                  # ✅ Utility scripts
    ├── test_data/                # ✅ V3 test data
    ├── tests/                    # ✅ V3 tests
    ├── infra/                    # ✅ Terraform
    ├── docker-compose.yml        # ✅ Deployment (port 3004)
    ├── .env                      # ✅ Local config
    ├── README_V3.md             # ✅ Start guide
    ├── HANDOFF_TO_COPILOT.md    # ✅ Setup guide
    ├── CHANGELOG_V3.md          # ✅ History
    ├── MANIFEST_V3.md           # ✅ Manifest
    └── CLEANUP_PLAN.md          # ✅ This file
```

---

## Cleanup Commands

After V3 is verified working, run these commands:

```bash
cd /Users/kumarlouhit/Documents/green-papaya

# Delete V1 files
rm -rf backend/
rm -rf frontend/
rm -rf memory/
rm -rf test_data/
rm -rf test_reports/
rm -rf tests/
rm auth_testing.md
rm test_result.md
rm README.md
rm green-papaya-v2-build-report.md

# Delete V2
rm -rf green-papaya-v2-production-foundation/

# Result should be:
# /green-papaya/
#   └── green-papaya-v3-production/
```

---

## After Cleanup: Final Directory Structure

```
green-papaya/
└── green-papaya-v3-production/
    ├── backend/
    ├── frontend/
    ├── docs/
    ├── memory/
    ├── scripts/
    ├── test_data/
    ├── tests/
    ├── infra/
    ├── docker-compose.yml
    ├── .env
    ├── README_V3.md
    ├── HANDOFF_TO_COPILOT.md
    ├── CHANGELOG_V3.md
    ├── MANIFEST_V3.md
    └── CLEANUP_PLAN.md
```

---

## Rollback Plan (If V3 Has Issues)

If V3 doesn't work:
1. Keep the original files in a backup location
2. Don't delete anything until V3 is fully verified
3. Run both systems in parallel for comparison
4. Delete only after reconciliation
