# Agent / model Training Lab (admin)
#
# Portal UI:  http://localhost:5173/backend   (separate BackendLayout — not the user app nav)
# Enter via:  Homepage footer → Admin → admin login
# API:        /api/training/*
#
# Flow (3 separate pages):
# 1. /backend/cases/:id/analyze — Upload PDF/DWG → Analyze (progress % popup) → Generate EOQ (full list)
#    DWG uses the same Autodesk APS path as user projects (Design Automation / Model Derivative).
#    Requires AUTODESK_CLIENT_ID + AUTODESK_CLIENT_SECRET in backend/.env (same as Production CAD).
# 2. /backend/cases/:id/original — Upload original EOQ (PDF / Excel / CSV / image) → gold list
# 3. /backend/cases/:id/evaluate — Compare AutoVAD vs original → training report
# Case hub: /backend/cases/:id
#
# Reports are meant to feed Phase-1+ agent specialization and later fine-tuning.
