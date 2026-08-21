# AutoVAD — Product Modules

This is the frozen module map for the product, including the **CAD & Civil 3D Intelligence Engine**.

## Module map

| Module | Status | What it does |
| --- | --- | --- |
| 1. Foundation | Done | Auth, projects, uploads, storage, DB |
| 2. Document AI Core | Done | PDF/Excel/CSV/image extract → CSI codes, units, confidence → chat → EOQ |
| 3. Trust Layer | Done (MVP) | Source refs, confidence, Open Source viewer jump |
| 4. Professional Tools | Done | Excel/CSV export, cost/SOR, **bid templates**, EOQ compare, drawing compare |
| 5. Product Layer | Done | Dashboard, analytics, reports, approvals, notifications, search, team share |
| 6. Operations | Done | Admin dashboard, health, jobs, storage metrics |
| 7. **CAD & Civil 3D Intelligence Engine** | **Done (wired)** | DXF/LandXML local; DWG via Autodesk APS; optional OpenAI quantity enrichment |
| 8. Cloud / AWS | Terraform ready | EC2, RDS, S3, CloudFront, WAF, IAM, SES, CloudWatch — deploy after app features |

---

## Module 7 — CAD & Civil 3D Intelligence Engine

```text
Upload DXF / DWG / LandXML / Civil 3D export
        │
        ▼
CAD Parser  ─── DXF: ezdxf (local)
            ─── LandXML: XML engine (local)
            ─── DWG / Civil 3D native: Autodesk APS (auth → OSS → Model Derivative → properties)
        │
        ▼
Extract layers, lines, polylines, blocks, dimensions, text, tables, LandXML assets
        │
        ▼
Quantity Engine (length / area / count by layer & block rules)
        │
        ▼
Optional OpenAI enrichment (OPENAI_API_KEY + CAD_OPENAI_ENRICHMENT)
        │
        ▼
EOQ merge + Excel/CSV + confidence + source refs
```

### Formats

| Format | Capability |
| --- | --- |
| **DXF** | Full local parse + quantity takeoff |
| **LandXML** | Alignments, surfaces, pipes, structures, cross-sections |
| **DWG** | Full APS pipeline when `AUTODESK_*` set; otherwise status `needs_autodesk` |
| **Civil 3D** | LandXML / JSON export; native DWG packages via APS |

### API

- `GET /api/ai/status` — OpenAI + APS readiness
- `GET /api/cad/capabilities`
- `GET /api/cad/projects/{id}`
- `POST /api/cad/documents/{id}/process`
- `POST /api/cad/projects/{id}/process-all`

### Config

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-terra
CAD_ENGINE_ENABLED=true
CAD_OPENAI_ENRICHMENT=true
AUTODESK_CLIENT_ID=
AUTODESK_CLIENT_SECRET=
AUTODESK_BUCKET_KEY=
AUTODESK_POLL_TIMEOUT_SECONDS=300
AUTODESK_POLL_INTERVAL_SECONDS=5
```

Restart the backend after changing `.env`.

---

## Still future

- Civil 3D corridor / assembly / sample-line volumes
- 3D solid volume takeoff
- CAD revision visual overlay compare
- AWS production deploy (after remaining product polish)
