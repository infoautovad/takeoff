// AutoVAD Design Automation plugin — build with AutoCAD .NET API (and optionally Civil 3D).
// Output: result.json next to the host drawing (WorkItem outputFile localName).
//
// Build notes (Windows + Visual Studio):
// 1) Install AutoCAD or use Autodesk.AutoCAD.* NuGet reference assemblies
// 2) Optionally reference AeccDbMgd / AecBaseMgd for Civil 3D objects
// 3) Build Release|x64 → copy DLL to Contents\ → zip PackageContents.xml + Contents as appbundle.zip

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.ApplicationServices.Core;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;

[assembly: CommandClass(typeof(AutoVadCivilTakeoff.Commands))]

namespace AutoVadCivilTakeoff
{
    public class Commands
    {
        [CommandMethod("AutoVadTakeoff", CommandFlags.Session)]
        public void RunTakeoff()
        {
            var doc = Application.DocumentManager.MdiActiveDocument;
            if (doc == null) return;

            var db = doc.Database;
            var layers = new List<object>();
            var lines = new List<object>();
            var polylines = new List<object>();
            var blocks = new List<object>();
            var texts = new List<object>();
            var circles = new List<object>();
            var hatches = new List<object>();
            int entityCount = 0;

            using (var tr = db.TransactionManager.StartTransaction())
            {
                var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                foreach (ObjectId id in lt)
                {
                    var layer = (LayerTableRecord)tr.GetObject(id, OpenMode.ForRead);
                    layers.Add(new { name = layer.Name, color = layer.Color.ColorIndex });
                }

                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
                foreach (ObjectId id in ms)
                {
                    entityCount++;
                    var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                    if (ent == null) continue;
                    var layer = ent.Layer;

                    switch (ent)
                    {
                        case Line ln:
                            lines.Add(new { layer, length = ln.Length });
                            break;
                        case Polyline pl:
                            polylines.Add(new { layer, length = pl.Length, area = pl.Area, closed = pl.Closed });
                            break;
                        case Polyline2d pl2:
                            polylines.Add(new { layer, length = 0.0, area = 0.0, closed = pl2.Closed });
                            break;
                        case Circle cir:
                            circles.Add(new { layer, radius = cir.Radius, area = Math.PI * cir.Radius * cir.Radius });
                            break;
                        case Arc arc:
                            circles.Add(new { layer, radius = arc.Radius, length = arc.Length, type = "arc" });
                            break;
                        case Hatch hatch:
                            try { hatches.Add(new { layer, area = hatch.Area }); } catch { /* ignore */ }
                            break;
                        case BlockReference br:
                            blocks.Add(new { name = br.Name, layer, type = "INSERT" });
                            break;
                        case DBText txt:
                            texts.Add(new { layer, text = txt.TextString });
                            break;
                        case MText mt:
                            texts.Add(new { layer, text = mt.Contents });
                            break;
                    }
                }
                tr.Commit();
            }

            var payload = new Dictionary<string, object>
            {
                ["units"] = db.Insunits.ToString(),
                ["layers"] = layers,
                ["lines"] = lines,
                ["polylines"] = polylines,
                ["blocks"] = blocks,
                ["texts"] = texts.Take(2000).ToList(),
                ["circles"] = circles,
                ["hatches"] = hatches,
                ["dimensions"] = new List<object>(),
                ["tables"] = new List<object>(),
                ["alignments"] = new List<object>(),
                ["pipes"] = new List<object>(),
                ["surfaces"] = new List<object>(),
                ["stats"] = new Dictionary<string, object>
                {
                    ["entity_count"] = entityCount,
                    ["layer_count"] = layers.Count,
                    ["line_count"] = lines.Count,
                    ["polyline_count"] = polylines.Count,
                    ["block_insert_count"] = blocks.Count,
                },
                ["summary"] = $"AutoVadTakeoff exported {entityCount} modelspace entities from Design Automation.",
            };

            var outPath = Path.Combine(Path.GetDirectoryName(doc.Name) ?? ".", "result.json");
            // WorkItem working folder is typically current directory
            if (string.IsNullOrWhiteSpace(Path.GetDirectoryName(doc.Name)))
                outPath = "result.json";
            // Prefer cwd result.json for DA output binding
            outPath = "result.json";
            File.WriteAllText(outPath, JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
            doc.Editor?.WriteMessage($"\nAutoVAD: wrote {outPath}");
        }
    }
}
