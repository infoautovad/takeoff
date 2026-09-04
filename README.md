# AutoVAD

AI copilot for civil engineers: upload road/civil documents, extract quantities, generate traceable EOQs (Estimate Of Quantities), estimate costs, compare revisions, and export Excel/CSV.

## Stack (current)

| Area | Technology |
| --- | --- |
| Frontend | Vue 3 + Vite + Vuetify + Pinia + Vue Router |
| Backend | FastAPI + SQLAlchemy + Pydantic |
| AI | OpenAI text + vision when configured, heuristic fallback when not configured |
| CAD | ezdxf (DXF), LandXML parser, Autodesk APS + Design Automation hooks for DWG/Civil 3D |
| PDF/Excel | PyMuPDF, pdfplumber, openpyxl |
| Database | SQLite local default (`backend/app/config.py`), PostgreSQL via `DATABASE_URL` |
| Storage | Local default, S3-ready backend path |
| Infra | Terraform source in `terraform/` (EC2, RDS, S3, CloudFront, WAF, SES, CloudWatch) |

Full module map: [`docs/MODULES.md`](docs/MODULES.md)

## Login modes (important)

1. **User app login**  
   Normal users create/manage projects, upload files, run Analyze/Process CAD, generate EOQ, review items, export, and chat.

2. **Admin training login**  
   Admin workflow used to compare original EOQ vs AutoVAD EOQ and generate training/evaluation reports in `/backend` pages.

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
Swagger docs: [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

App: [http://localhost:5173](http://localhost:5173)

## Runtime config essentials

Copy `backend/.env.example` to `backend/.env` and set values as needed:

- `OPENAI_API_KEY` for full PDF plan-sheet vision takeoff
- `AUTODESK_CLIENT_ID` / `AUTODESK_CLIENT_SECRET` for DWG APS/Design Automation processing
- `DATABASE_URL` (SQLite default or PostgreSQL)

## What is built

- Auth + roles (admin, PM, engineer, QS, reviewer, client)
- Projects, uploads, source viewer, document analysis
- Analyze -> EOQ generation -> Excel/CSV export
- Bid template upload + template mapping
- Cost estimator (SOR upload + estimate)
- EOQ compare + drawing revision compare
- Reports, approvals, notifications, search, analytics
- Admin dashboard + training/evaluation portal
- CAD/Civil 3D intelligence path (DXF/LandXML local, DWG via APS)

