# AutoVAD

AI Copilot for Civil Engineers — upload road/civil documents, extract quantities, generate traceable EOQs (Estimate Of Quantities), estimate cost, compare revisions, and export Excel/CSV.

## Stack (as planned)

| Area | Technology |
| --- | --- |
| Frontend | Vue 3 + Vite + Vuetify + Pinia + Vue Router |
| Backend | FastAPI + SQLAlchemy + Pydantic |
| AI | Heuristic civil extractor now; OpenAI optional later |
| CAD | ezdxf (DXF), LandXML parser, Autodesk APS hooks for DWG/Civil 3D |
| PDF/Excel | PyMuPDF, pdfplumber, openpyxl |
| Database | SQLite locally now → PostgreSQL / AWS RDS later |
| Storage | Local now → AWS S3 later |
| Infra | Terraform under `terraform/` (EC2, RDS, S3, CloudFront, WAF, SES, CloudWatch) |

> Docker was removed. It was only an optional local Postgres helper and is **not** part of your required stack. Local development uses **SQLite** by default.

Full module map: [`docs/MODULES.md`](docs/MODULES.md)

## Quick start

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

API: [http://127.0.0.1:8001](http://127.0.0.1:8001)  
Docs: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: [http://localhost:5173](http://localhost:5173)

## What is built

- Auth + roles (admin, PM, engineer, QS, reviewer, client)
- Projects, uploads, document viewer with page jump / Open Source
- Analyze → EOQ (Estimate Of Quantities) → Excel/CSV export
- AI chat (heuristic now)
- Cost estimator (SOR upload + estimate)
- EOQ compare + drawing revision compare
- Reports, approvals, notifications, global search
- Analytics charts
- Admin dashboard (users, jobs, storage, health)
- **CAD & Civil 3D Intelligence Engine** (DXF + LandXML now; DWG/Civil 3D via APS next)

## CAD / Civil 3D

Project tab **CAD / Civil 3D**:

1. Upload `.dxf`, `.dwg`, `.xml`/`.landxml`, or Civil JSON  
2. Click **Process CAD files**  
3. Review extracted layers / blocks / quantities  
4. **Generate EOQ** (merges document AI + CAD quantities)

Native DWG later:

```env
AUTODESK_CLIENT_ID=
AUTODESK_CLIENT_SECRET=
AUTODESK_BUCKET_KEY=
```

## OpenAI later (optional)

Leave empty for now. When ready:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

Then restart backend. Until then the app uses the built-in heuristic analyzer.

## Admin access

Register with role `admin`, or change a user role from Admin page after logging in as an admin account.
