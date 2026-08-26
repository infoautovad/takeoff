// AutoVAD Design Automation plugin — AutoCAD .NET API + optional Civil 3D.
// Writes result.json with geometry Civil StationOffset needs:
//   alignments (sampled), pipes (start/end XY + stations), blocks (insert + attribs),
//   polylines (vertices), lines (start/end), texts (model + paper-space callouts).

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
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
            var alignments = new List<object>();
            var pipes = new List<object>();
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
                ExportSpace(tr, (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead),
                    "model", ref entityCount, lines, polylines, blocks, texts, circles, hatches);

                // Paper-space sheet labels (STA / offset callouts)
                var ltLayout = (DBDictionary)tr.GetObject(db.LayoutDictionaryId, OpenMode.ForRead);
                foreach (var entry in ltLayout)
                {
                    if (string.Equals(entry.Key, "Model", StringComparison.OrdinalIgnoreCase))
                        continue;
                    try
                    {
                        var layout = (Layout)tr.GetObject(entry.Value, OpenMode.ForRead);
                        var btr = (BlockTableRecord)tr.GetObject(layout.BlockTableRecordId, OpenMode.ForRead);
                        ExportSpace(tr, btr, "paper", ref entityCount, lines, polylines, blocks, texts, circles, hatches);
                    }
                    catch { /* ignore layout */ }
                }

                TryExportCivil(tr, alignments, pipes, blocks);
                tr.Commit();
            }

            var payload = new Dictionary<string, object>
            {
                ["units"] = db.Insunits.ToString(),
                ["layers"] = layers,
                ["lines"] = lines,
                ["polylines"] = polylines,
                ["blocks"] = blocks,
                ["texts"] = texts.Take(4000).ToList(),
                ["circles"] = circles,
                ["hatches"] = hatches,
                ["dimensions"] = new List<object>(),
                ["tables"] = new List<object>(),
                ["alignments"] = alignments,
                ["pipes"] = pipes,
                ["surfaces"] = new List<object>(),
                ["stats"] = new Dictionary<string, object>
                {
                    ["entity_count"] = entityCount,
                    ["layer_count"] = layers.Count,
                    ["line_count"] = lines.Count,
                    ["polyline_count"] = polylines.Count,
                    ["block_insert_count"] = blocks.Count,
                    ["alignment_count"] = alignments.Count,
                    ["pipe_count"] = pipes.Count,
                    ["civil_loaded"] = alignments.Count > 0 || pipes.Count > 0,
                },
                ["summary"] = $"AutoVadTakeoff exported {entityCount} entities, {alignments.Count} alignments, {pipes.Count} pipes, {blocks.Count} blocks.",
            };

            File.WriteAllText("result.json", JsonSerializer.Serialize(payload, new JsonSerializerOptions { WriteIndented = true }));
            doc.Editor?.WriteMessage($"\nAutoVAD: wrote result.json");
        }

        static void ExportSpace(
            Transaction tr,
            BlockTableRecord space,
            string spaceName,
            ref int entityCount,
            List<object> lines,
            List<object> polylines,
            List<object> blocks,
            List<object> texts,
            List<object> circles,
            List<object> hatches)
        {
            foreach (ObjectId id in space)
            {
                entityCount++;
                var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                if (ent == null) continue;
                var layer = ent.Layer;

                switch (ent)
                {
                    case Line ln:
                        lines.Add(new
                        {
                            layer,
                            length = ln.Length,
                            start = new[] { ln.StartPoint.X, ln.StartPoint.Y },
                            end = new[] { ln.EndPoint.X, ln.EndPoint.Y },
                        });
                        break;
                    case Polyline pl:
                        polylines.Add(ReadPolyline(pl, layer));
                        break;
                    case Polyline2d pl2:
                        polylines.Add(ReadPolyline2d(tr, pl2, layer));
                        break;
                    case Polyline3d pl3:
                        polylines.Add(ReadPolyline3d(tr, pl3, layer));
                        break;
                    case Circle cir:
                        circles.Add(new
                        {
                            layer,
                            radius = cir.Radius,
                            area = Math.PI * cir.Radius * cir.Radius,
                            center = new[] { cir.Center.X, cir.Center.Y },
                        });
                        break;
                    case Arc arc:
                        circles.Add(new { layer, radius = arc.Radius, length = arc.Length, type = "arc" });
                        break;
                    case Hatch hatch:
                        try { hatches.Add(new { layer, area = hatch.Area }); } catch { /* ignore */ }
                        break;
                    case BlockReference br:
                        blocks.Add(ReadBlock(tr, br, layer));
                        break;
                    case DBText txt:
                        texts.Add(new
                        {
                            layer,
                            text = txt.TextString,
                            insert = new[] { txt.Position.X, txt.Position.Y },
                            space = spaceName,
                        });
                        break;
                    case MText mt:
                        texts.Add(new
                        {
                            layer,
                            text = mt.Contents,
                            insert = new[] { mt.Location.X, mt.Location.Y },
                            space = spaceName,
                        });
                        break;
                }
            }
        }

        static object ReadPolyline(Polyline pl, string layer)
        {
            var pts = new List<double[]>();
            for (int i = 0; i < pl.NumberOfVertices; i++)
            {
                var p = pl.GetPoint2dAt(i);
                pts.Add(new[] { p.X, p.Y });
            }
            return new
            {
                layer,
                name = layer,
                length = pl.Length,
                area = SafeArea(pl),
                closed = pl.Closed,
                vertices = pts.Count,
                points = pts,
            };
        }

        static double SafeArea(Polyline pl)
        {
            try { return pl.Area; } catch { return 0; }
        }

        static object ReadPolyline2d(Transaction tr, Polyline2d pl2, string layer)
        {
            var pts = new List<double[]>();
            foreach (ObjectId vid in pl2)
            {
                var v = tr.GetObject(vid, OpenMode.ForRead) as Vertex2d;
                if (v != null)
                    pts.Add(new[] { v.Position.X, v.Position.Y });
            }
            return new { layer, name = layer, length = 0.0, closed = pl2.Closed, vertices = pts.Count, points = pts };
        }

        static object ReadPolyline3d(Transaction tr, Polyline3d pl3, string layer)
        {
            var pts = new List<double[]>();
            foreach (ObjectId vid in pl3)
            {
                var v = tr.GetObject(vid, OpenMode.ForRead) as PolylineVertex3d;
                if (v != null)
                    pts.Add(new[] { v.Position.X, v.Position.Y });
            }
            return new { layer, name = layer, length = 0.0, vertices = pts.Count, points = pts };
        }

        static object ReadBlock(Transaction tr, BlockReference br, string layer)
        {
            var attribs = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            try
            {
                foreach (ObjectId aid in br.AttributeCollection)
                {
                    var att = tr.GetObject(aid, OpenMode.ForRead) as AttributeReference;
                    if (att == null || string.IsNullOrWhiteSpace(att.Tag)) continue;
                    attribs[att.Tag] = att.TextString ?? "";
                    attribs[att.Tag.ToUpperInvariant()] = att.TextString ?? "";
                }
            }
            catch { /* no attribs */ }

            string GetAttr(params string[] tags)
            {
                foreach (var t in tags)
                {
                    if (attribs.TryGetValue(t, out var v) && !string.IsNullOrWhiteSpace(v))
                        return v;
                }
                return null;
            }

            var insert = new[] { br.Position.X, br.Position.Y };
            return new
            {
                name = br.Name,
                layer,
                type = "INSERT",
                insert,
                position = insert,
                rotation = br.Rotation,
                attributes = attribs,
                station = GetAttr("STATION", "STA", "STN", "RAWSTA"),
                side = GetAttr("SIDE", "DIR", "HAND"),
                offset = GetAttr("OFFSET", "OFF", "OS"),
            };
        }

        /// <summary>
        /// Late-bound Civil 3D export so the DLL still loads on AutoCAD-only DA engines.
        /// Uses Alignment.StationOffset / PointLocation and pipe-network locations.
        /// </summary>
        static void TryExportCivil(Transaction tr, List<object> alignments, List<object> pipes, List<object> blocks)
        {
            try
            {
                Type civAppType = null;
                foreach (var assy in AppDomain.CurrentDomain.GetAssemblies())
                {
                    civAppType = assy.GetType("Autodesk.Civil.ApplicationServices.CivilApplication");
                    if (civAppType != null) break;
                }
                if (civAppType == null) return;

                var civDoc = civAppType.GetProperty("ActiveDocument", BindingFlags.Public | BindingFlags.Static)
                    ?.GetValue(null, null);
                if (civDoc == null) return;

                ExportCivilAlignments(tr, civDoc, alignments);
                ExportCivilNetworks(tr, civDoc, pipes, blocks, alignments);
            }
            catch
            {
                // Civil 3D not available — AutoCAD geometry already exported
            }
        }

        static void ExportCivilAlignments(Transaction tr, object civDoc, List<object> alignments)
        {
            try
            {
                dynamic doc = civDoc;
                foreach (dynamic oid in doc.GetAlignmentIds())
                {
                    dynamic al = tr.GetObject((ObjectId)oid, OpenMode.ForRead);
                    string aname = Convert.ToString(al.Name);
                    double sta0 = ToDouble(al, "StartingStation");
                    double sta1 = ToDouble(al, "EndingStation");
                    double alen = ToDouble(al, "Length");
                    if (sta1 <= sta0 && alen > 0) sta1 = sta0 + alen;

                    var pts = SampleAlignment(al, sta0, sta1, alen);
                    alignments.Add(new
                    {
                        name = aname,
                        layer = aname,
                        length = alen,
                        sta_start = sta0,
                        start_station = sta0,
                        points = pts,
                        source = "civil3d_alignment",
                    });
                }
            }
            catch { /* alignments API mismatch */ }
        }

        static List<double[]> SampleAlignment(dynamic al, double sta0, double sta1, double alen)
        {
            var pts = new List<double[]>();
            double span = Math.Max(alen, sta1 - sta0);
            if (span <= 0) span = 100;
            double step = Math.Max(10.0, span / 80.0);
            for (double s = sta0; s <= sta1 + 0.01; s += step)
            {
                var xy = PointAtStation(al, s);
                if (xy != null) pts.Add(xy);
            }
            var last = PointAtStation(al, sta1);
            if (last != null) pts.Add(last);
            return pts;
        }

        static double[] PointAtStation(dynamic al, double station)
        {
            try
            {
                double x = 0, y = 0;
                al.PointLocation(station, 0.0, ref x, ref y);
                return new[] { x, y };
            }
            catch
            {
                try
                {
                    double x = 0, y = 0, z = 0;
                    al.PointLocation(station, 0.0, 0.0, ref x, ref y, ref z);
                    return new[] { x, y };
                }
                catch { return null; }
            }
        }

        static void ExportCivilNetworks(Transaction tr, object civDoc, List<object> pipes, List<object> blocks, List<object> alignments)
        {
            try
            {
                dynamic doc = civDoc;
                dynamic firstAlign = null;
                try
                {
                    foreach (dynamic oid in doc.GetAlignmentIds())
                    {
                        firstAlign = tr.GetObject((ObjectId)oid, OpenMode.ForRead);
                        break;
                    }
                }
                catch { /* no alignments */ }

                foreach (dynamic nid in doc.GetPipeNetworkIds())
                {
                    dynamic net = tr.GetObject((ObjectId)nid, OpenMode.ForRead);
                    string netName = SafeName(net);
                    dynamic refAl = firstAlign;
                    try { if (net.ReferenceAlignmentId != ObjectId.Null) refAl = tr.GetObject(net.ReferenceAlignmentId, OpenMode.ForRead); } catch { }

                    try
                    {
                        foreach (dynamic pid in net.GetPipeIds())
                        {
                            dynamic pipe = tr.GetObject((ObjectId)pid, OpenMode.ForRead);
                            var start = Point3(pipe, "StartPoint");
                            var end = Point3(pipe, "EndPoint");
                            double[] staOffStart = StationOffsetOf(refAl, start);
                            double[] staOffEnd = StationOffsetOf(refAl, end);
                            pipes.Add(new
                            {
                                name = SafeName(pipe),
                                layer = netName,
                                network = netName,
                                length = ToDouble(pipe, "Length2DCenterToCenter", "Length2D", "Length3D"),
                                diameter = ToDouble(pipe, "InnerDiameterOrWidth", "Diameter"),
                                part_size = SafeName(pipe),
                                start,
                                end,
                                points = (start != null && end != null) ? new[] { start, end } : null,
                                sta_start = staOffStart != null ? staOffStart[0] : (double?)null,
                                sta_end = staOffEnd != null ? staOffEnd[0] : (double?)null,
                                offset = staOffStart != null ? staOffStart[1] : (double?)null,
                                side = SideFromCivilOffset(staOffStart != null ? staOffStart[1] : (double?)null),
                                source = "civil3d_pipe",
                            });
                        }
                    }
                    catch { /* pipes */ }

                    try
                    {
                        foreach (dynamic sid in net.GetStructureIds())
                        {
                            dynamic st = tr.GetObject((ObjectId)sid, OpenMode.ForRead);
                            var loc = Point3(st, "Location", "Position");
                            if (loc == null)
                            {
                                try { loc = new[] { (double)st.Easting, (double)st.Northing }; } catch { }
                            }
                            double[] so = StationOffsetOf(refAl, loc);
                            blocks.Add(new
                            {
                                name = SafeName(st),
                                layer = netName,
                                type = "Structure",
                                network = netName,
                                description = SafeName(st),
                                insert = loc,
                                position = loc,
                                station = so != null ? so[0] : (double?)null,
                                offset = so != null ? so[1] : (double?)null,
                                offset_ft = so != null ? Math.Abs(so[1]) : (double?)null,
                                side = SideFromCivilOffset(so != null ? so[1] : (double?)null),
                                source = "civil3d_structure",
                            });
                        }
                    }
                    catch { /* structures */ }
                }
            }
            catch { /* networks API mismatch */ }
        }

        static double[] StationOffsetOf(dynamic alignment, double[] xy)
        {
            if (alignment == null || xy == null || xy.Length < 2) return null;
            try
            {
                double sta = 0, off = 0;
                alignment.StationOffset(xy[0], xy[1], ref sta, ref off);
                return new[] { sta, off };
            }
            catch { return null; }
        }

        static string SideFromCivilOffset(double? signed)
        {
            if (signed == null) return null;
            if (Math.Abs(signed.Value) < 0.05) return "CL";
            return signed.Value > 0 ? "RT" : "LT";
        }

        static double[] Point3(dynamic obj, params string[] names)
        {
            foreach (var n in names)
            {
                try
                {
                    var p = obj.GetType().GetProperty(n)?.GetValue(obj, null);
                    if (p == null) continue;
                    double x = Convert.ToDouble(p.GetType().GetProperty("X")?.GetValue(p, null));
                    double y = Convert.ToDouble(p.GetType().GetProperty("Y")?.GetValue(p, null));
                    return new[] { x, y };
                }
                catch { /* try next */ }
            }
            return null;
        }

        static double ToDouble(dynamic obj, params string[] names)
        {
            foreach (var n in names)
            {
                try
                {
                    var v = obj.GetType().GetProperty(n)?.GetValue(obj, null);
                    if (v != null) return Convert.ToDouble(v);
                }
                catch { }
            }
            return 0;
        }

        static string SafeName(dynamic obj)
        {
            try { return Convert.ToString(obj.Name); } catch { return "Civil"; }
        }
    }
}
