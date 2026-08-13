import ezdxf
from pathlib import Path

p = Path("storage/sample_road.dxf")
p.parent.mkdir(exist_ok=True)
doc = ezdxf.new("R2010")
msp = doc.modelspace()
msp.add_lwpolyline([(0, 0), (100, 0), (100, 2), (0, 2)], close=True, dxfattribs={"layer": "KERB"})
msp.add_line((0, 10), (250, 10), dxfattribs={"layer": "EOP"})
msp.add_line((0, 20), (250, 20), dxfattribs={"layer": "CENTERLINE"})
if "CULVERT" not in doc.blocks:
    block = doc.blocks.new("CULVERT")
    block.add_circle((0, 0), 0.5)
msp.add_blockref("CULVERT", (80, 0), dxfattribs={"layer": "CULVERT"})
msp.add_blockref("CULVERT", (160, 0), dxfattribs={"layer": "CULVERT"})
msp.add_text("Road width 7.5m", dxfattribs={"layer": "NOTES", "height": 1}).set_placement((10, 30))
doc.saveas(p)
print("wrote", p.resolve())
