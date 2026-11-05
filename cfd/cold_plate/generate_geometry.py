"""Create partitioned CAD in mm and conformal hex meshes in m. No CFD solve."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path

from prepare_cases import write_json

GROUPS = {"solid": (3, 1), "fluid": (3, 2), "inlet": (2, 11),
          "outlet": (2, 12), "heater": (2, 13), "solid_fluid": (2, 14),
          "adiabatic_roof": (2, 15), "adiabatic_solid": (2, 16)}
# Cell counts in x, channel width, channel depth, web, base and side margin.
# These are starter grids, not demonstrated mesh-independent settings.
MESHES = {"smoke": (8, 2, 2, 1, 1, 2), "coarse": (80, 4, 8, 2, 4, 6),
          "medium": (160, 8, 16, 4, 8, 12), "fine": (320, 16, 32, 8, 16, 24)}


def check_spec(spec):
    g = spec["geometry_m"]
    for key in ["length", "width", "channel_width", "channel_depth", "web", "base", "side_margin"]:
        if isinstance(g[key], bool) or not math.isfinite(g[key]) or g[key] <= 0:
            raise ValueError(f"Invalid geometry: {key}")
    n = g["channel_count"]
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError("channel_count must be an integer >= 2")
    occupied = n*g["channel_width"] + (n-1)*g["web"] + 2*g["side_margin"]
    if not math.isclose(occupied, g["width"], abs_tol=1e-12):
        raise ValueError("Channels, webs and margins do not fill the width")
    return g


def build(spec, output, mesh_level="none"):
    import gmsh
    g = check_spec(spec)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    L, W, w, d, s, t, e = [g[k]*1000 for k in
                            ["length", "width", "channel_width", "channel_depth", "web", "base", "side_margin"]]
    n = g["channel_count"]
    strips = [(0., e, "margin")]
    for i in range(n):
        y = e + i*(w+s)
        strips.append((y, y+w, "channel"))
        if i < n-1:
            strips.append((y+w, y+w+s, "web"))
    strips.append((W-e, W, "margin"))
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setNumber("General.NumThreads", 1)
        gmsh.option.setString("Geometry.OCCTargetUnit", "MM")
        gmsh.model.add(spec["case_id"])
        occ = gmsh.model.occ
        boxes, original_roles = [], []
        for a, b, kind in strips:
            boxes.append((3, occ.addBox(0, a, 0, L, b-a, t)))
            original_roles.append("solid")
            boxes.append((3, occ.addBox(0, a, t, L, b-a, d)))
            original_roles.append("fluid" if kind == "channel" else "solid")
        _, mapping = occ.fragment(boxes[:1], boxes[1:])
        occ.synchronize()
        roles = {}
        for original, mapped in zip(original_roles, mapping):
            for dim, tag in mapped:
                if dim == 3:
                    if tag in roles and roles[tag] != original:
                        raise ValueError("Overlapping solid/fluid volumes")
                    roles[tag] = original
        if set(roles) != {tag for _, tag in gmsh.model.getEntities(3)}:
            raise ValueError("Unclassified volume")
        groups = defaultdict(list)
        adjacency = defaultdict(list)
        for tag, role in roles.items():
            groups[role].append(tag)
            for _, face in gmsh.model.getBoundary([(3, tag)], oriented=False):
                adjacency[face].append(role)
        for face, adjacent in adjacency.items():
            center = occ.getCenterOfMass(2, face)
            if len(adjacent) == 2:
                if set(adjacent) == {"solid", "fluid"}:
                    groups["solid_fluid"].append(face)
                elif adjacent != ["solid", "solid"]:
                    raise ValueError("Unexpected internal interface")
            elif len(adjacent) == 1:
                if adjacent[0] == "fluid":
                    if abs(center[0]) < 1e-7:
                        groups["inlet"].append(face)
                    elif abs(center[0]-L) < 1e-7:
                        groups["outlet"].append(face)
                    elif abs(center[2]-(t+d)) < 1e-7:
                        groups["adiabatic_roof"].append(face)
                    else:
                        raise ValueError("Unclassified fluid boundary")
                else:
                    groups["heater" if abs(center[2]) < 1e-7 else "adiabatic_solid"].append(face)
            else:
                raise ValueError("Non-manifold face")
        if len(groups["fluid"]) != n or len(groups["inlet"]) != n or len(groups["outlet"]) != n:
            raise ValueError("Incorrect channel topology")
        report = {"case_id": spec["case_id"], "gmsh_version": gmsh.__version__,
                  "input_object_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
                  "status": "Geometry checks only. No CFD solution.",
                  "cad_units": "mm", "mesh_units": "m", "groups": {}}
        for name, (dim, physical_id) in GROUPS.items():
            tags = sorted(groups[name])
            if not tags:
                raise ValueError(f"Empty physical group: {name}")
            gmsh.model.addPhysicalGroup(dim, tags, physical_id, name)
            measure = sum(occ.getMass(dim, tag) for tag in tags) * 1e-3**dim
            report["groups"][name] = {"dimension": dim, "physical_id": physical_id,
                                      "entity_tags": tags, "measure_si": measure}
        expected = {"fluid": "fluid_volume_m3", "solid": "solid_volume_m3",
                    "inlet": "inlet_area_m2", "outlet": "inlet_area_m2", "heater": "heater_area_m2",
                    "solid_fluid": "interface_area_m2", "adiabatic_roof": "roof_area_m2"}
        for group, key in expected.items():
            if not math.isclose(report["groups"][group]["measure_si"], spec["analytical"][key], rel_tol=1e-8):
                raise ValueError(f"Geometry measure mismatch: {group}")
        report["surface_map"] = {
            name: [{"tag": face, "centroid_m": [v/1000 for v in occ.getCenterOfMass(2, face)],
                    "area_m2": occ.getMass(2, face)/1e6} for face in sorted(groups[name])]
            for name, (dim, _) in GROUPS.items() if dim == 2}
        gmsh.option.setString("Geometry.OCCSTEPDescription", "Idealized straight-channel research geometry. Units: mm.")
        gmsh.option.setString("Geometry.OCCSTEPAuthor", "")
        gmsh.option.setString("Geometry.OCCSTEPOrganization", "")
        gmsh.option.setString("Geometry.OCCSTEPTimeStamp", "2026-11-04T00:00:00")
        gmsh.write(str(output / "domains.step"))
        gmsh.write(str(output / "domains_mm.brep"))
        if mesh_level != "none":
            nx, nw, nd, ns, nt, ne = MESHES[mesh_level]
            for _, edge in gmsh.model.getEntities(1):
                bounds = gmsh.model.getBoundary([(1, edge)], oriented=False)
                points = [gmsh.model.getValue(0, tag, []) for _, tag in bounds]
                delta = [abs(points[1][i]-points[0][i]) for i in range(3)]
                axis = max(range(3), key=delta.__getitem__)
                center = occ.getCenterOfMass(1, edge)
                if axis == 0:
                    count = nx
                elif axis == 2:
                    count = nt if center[2] < t else nd
                else:
                    kind = next(kind for a, b, kind in strips if a < center[1] < b)
                    count = {"channel": nw, "web": ns, "margin": ne}[kind]
                gmsh.model.mesh.setTransfiniteCurve(edge, count+1)
            for _, face in gmsh.model.getEntities(2):
                gmsh.model.mesh.setTransfiniteSurface(face)
                gmsh.model.mesh.setRecombine(2, face)
            for tag in roles:
                gmsh.model.mesh.setTransfiniteVolume(tag)
            gmsh.model.mesh.generate(3)
            types, tags, _ = gmsh.model.mesh.getElements(3)
            if list(types) != [5]:
                raise ValueError("Expected first-order hexahedra only")
            all_tags = tags[0]
            qualities = gmsh.model.mesh.getElementQualities(all_tags, "minSJ")
            volumes = gmsh.model.mesh.getElementQualities(all_tags, "volume")
            if min(qualities) <= 0 or min(volumes) <= 0:
                raise ValueError("Inverted or degenerate mesh element")
            expected_cells = nx * (n*nw + (n-1)*ns + 2*ne) * (nt+nd)
            if len(all_tags) != expected_cells:
                raise ValueError("Unexpected mesh cell count")
            report["mesh"] = {"level": mesh_level, "hex_cells": len(all_tags),
                              "min_scaled_jacobian": float(min(qualities)),
                              "volume_m3": float(sum(volumes))*1e-9,
                              "cell_counts_x_width_depth_web_base_margin": MESHES[mesh_level],
                              "solver_import_verified": False, "mesh_independence_verified": False}
            gmsh.option.setNumber("Mesh.ScalingFactor", .001)
            gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
            gmsh.option.setNumber("Mesh.Binary", 1)
            gmsh.write(str(output / "mesh_si.msh"))
        report["files_sha256"] = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.iterdir()) if p.name in ["domains.step", "domains_mm.brep", "mesh_si.msh"]}
        write_json(output / "geometry_report.json", report)
        return report
    finally:
        gmsh.finalize()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mesh", choices=["none", *MESHES], default="none")
    args = parser.parse_args()
    result = build(json.loads(args.case.read_text()), args.output, args.mesh)
    print(json.dumps({"case_id": result["case_id"], "checks": "passed", "mesh": result.get("mesh")}, indent=2))
