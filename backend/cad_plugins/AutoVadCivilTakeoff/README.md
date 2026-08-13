# AutoVadCivilTakeoff (Design Automation AppBundle)

Optional .NET plugin for richer DWG takeoff inside Autodesk **Design Automation** (cloud AutoCAD).

AutoVAD works **without** this plugin: it uses a script activity that converts DWG → DXF in the cloud, then parses geometry locally.

## When to build this

Build and place `appbundle.zip` here when you want the plugin activity (`AutoVadTakeoff` → `result.json`) instead of DXF export.

## Build (Windows)

1. Install Visual Studio + .NET Framework / SDK compatible with your AutoCAD year.
2. Create a Class Library project targeting **.NET Framework 4.8** (or the version required by your AutoCAD API).
3. Reference AutoCAD libraries (`AcCoreMgd`, `AcDbMgd`, `AcMgd`) from your AutoCAD install, **Copy Local = False**.
4. Optional Civil 3D: also reference `AeccDbMgd`, `AecBaseMgd` and extend `Commands.cs` for alignments/pipes/surfaces.
5. Build **x64 Release**, copy `AutoVadCivilTakeoff.dll` into `Contents/`.
6. Zip `PackageContents.xml` + `Contents/` as **`appbundle.zip`** in this folder  
   (or run from backend: `python -c "from app.services.cad.design_automation import package_appbundle_from_folder; from pathlib import Path; print(package_appbundle_from_folder(Path('cad_plugins/AutoVadCivilTakeoff')))"`).
7. In the UI: **CAD → Setup Design Automation**, or `POST /api/cad/design-automation/setup`.

## APS app settings

Enable on your APS app:

- Model Derivative API
- Data Management API
- **Design Automation API**

Scopes used: `data:read data:write data:create bucket:create bucket:read viewables:read code:all`
