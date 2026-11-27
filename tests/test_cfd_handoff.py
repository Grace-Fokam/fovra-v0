"""Geometry, data provenance and verification-utility checks, not CFD validation."""

import csv
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cfd/cold_plate"))
from prepare_cases import SELECTION, prepare
from generate_geometry import build, check_spec, GROUPS
from check_solution import FIELDS, assess, grid_convergence


def case(name="N0_nominal"):
    return json.loads((ROOT / "cfd/cold_plate/inputs/cases" / f"{name}.json").read_text())


def test_recreate_recorded_inputs(tmp_path):
    prepare(tmp_path)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (ROOT/"cfd/cold_plate/inputs"/path.relative_to(tmp_path)).read_bytes()


def test_recorded_selection_and_independent_dimensions():
    with (ROOT / "results/cold_plate/grid.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    for name, candidate_id, _ in SELECTION:
        spec = case(name)
        row = next(r for r in rows if r["case"] == "nominal" and int(r["candidate_id"]) == candidate_id)
        assert spec["recorded_design"] == {k: float(row[k]) for k in spec["recorded_design"]}
        g = spec["geometry_m"]
        n = g["channel_count"]
        assert g["width"] == pytest.approx(n*g["channel_width"]+(n-1)*g["web"]+2*g["side_margin"])
        assert spec["analytical"]["fluid_volume_m3"] == pytest.approx(n*g["length"]*g["channel_width"]*g["channel_depth"])
        assert spec["boundary_inputs"]["heat_flux_w_m2"]*g["length"]*g["width"] == pytest.approx(100)
        assert spec["cfd_results"] is None
        assert all(v is None for v in spec["unknown_partner_inputs"].values())
    n0 = case()
    assert n0["geometry_m"]["side_margin"] == pytest.approx(.0011)
    assert n0["analytical"]["solid_volume_m3"] == pytest.approx(7.088e-6)
    assert n0["analytical"]["fluid_volume_m3"] == pytest.approx(6.912e-6)


def test_invalid_packing_rejected():
    spec = case()
    spec["geometry_m"]["channel_count"] = 49
    with pytest.raises(ValueError, match="fill the width"):
        check_spec(spec)


@pytest.mark.parametrize("name", ["N0_nominal", "G1_narrow", "G2_shallow", "G3_thicker_web", "G4_thicker_base"])
def test_cad_and_mesh_round_trip(name, tmp_path):
    gmsh = pytest.importorskip("gmsh")
    spec = case(name)
    report = build(spec, tmp_path, "smoke")
    assert report["mesh"]["min_scaled_jacobian"] > .99
    assert report["mesh"]["volume_m3"] == pytest.approx(sum(spec["analytical"][k] for k in ["fluid_volume_m3", "solid_volume_m3"]))
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.option.setString("Geometry.OCCTargetUnit", "M")
        gmsh.open(str(tmp_path / "domains.step"))
        g = spec["geometry_m"]
        bbox = gmsh.model.getBoundingBox(-1, -1)
        assert bbox == pytest.approx((0, 0, 0, g["length"], g["width"], g["base"]+g["channel_depth"]), abs=2e-7)
        volume = sum(gmsh.model.occ.getMass(3, tag) for _, tag in gmsh.model.getEntities(3))
        assert volume == pytest.approx(g["length"]*g["width"]*(g["base"]+g["channel_depth"]), rel=1e-8)
        gmsh.clear()
        gmsh.open(str(tmp_path / "mesh_si.msh"))
        assert gmsh.model.getBoundingBox(-1, -1) == pytest.approx((0, 0, 0, g["length"], g["width"], g["base"]+g["channel_depth"]), abs=1e-12)
        for name, (dim, tag) in GROUPS.items():
            assert gmsh.model.getPhysicalName(dim, tag) == name
        solid_nodes = set(gmsh.model.mesh.getNodesForPhysicalGroup(3, 1)[0])
        fluid_nodes = set(gmsh.model.mesh.getNodesForPhysicalGroup(3, 2)[0])
        interface_nodes = set(gmsh.model.mesh.getNodesForPhysicalGroup(2, 14)[0])
        assert interface_nodes
        assert interface_nodes <= solid_nodes & fluid_nodes
    finally:
        gmsh.finalize()


def test_conservation_checker_accepts_consistent_integrals_and_rejects_bad_balance():
    row = {name: 0 for name in FIELDS}
    row.update(case_id="synthetic_utility_test", physics_variant="B0", mesh_level="unit_test",
               cell_count=100, solver_version="synthetic", mass_in_kg_s=.001,
               mass_out_kg_s=.001, heater_w=100, enthalpy_gain_w=100,
               interface_solid_to_fluid_w=100, interface_fluid_from_solid_w=100,
               inlet_k=298.15, outlet_bulk_k=310, base_max_k=312, base_mean_k=306,
               p_in_area_pa=50, p_out_area_pa=0, pressure_gradient_pa_m=-500)
    assert assess(row)["integral_checks_pass"]
    row["enthalpy_gain_w"] = 97
    assert not assess(row)["integral_checks_pass"]
    row["base_max_k"] = ""
    with pytest.raises(ValueError, match="Missing"):
        assess(row)


def test_gci_known_second_order_sequence_and_bad_sequences():
    result = grid_convergence(14., 11., 10.25)
    assert result["observed_order"] == pytest.approx(2)
    assert result["extrapolated"] == pytest.approx(10)
    assert result["fine_gci_absolute"] == pytest.approx(.3125)
    for values in [(10, 11, 10.5), (10, 10, 10), (10, 11, 14)]:
        with pytest.raises(ValueError):
            grid_convergence(*values)


def test_water_table_reproducibility_and_interpolation():
    pytest.importorskip("CoolProp")
    from CoolProp.CoolProp import PropsSI
    with (ROOT / "cfd/cold_plate/inputs/water_101325pa.csv").open() as stream:
        rows = [{k: float(v) for k, v in r.items()} for r in csv.DictReader(stream)]
    props = {"rho_kg_m3": "Dmass", "mu_pa_s": "VISCOSITY", "cp_j_kgk": "Cpmass",
             "k_w_mk": "CONDUCTIVITY", "h_j_kg": "Hmass"}
    for row in rows:
        for key, prop in props.items():
            assert row[key] == pytest.approx(PropsSI(prop, "T", row["temperature_k"], "P", 101325, "HEOS::Water"), rel=1e-9)
    for low, high in zip(rows, rows[1:]):
        temperature = (low["temperature_k"]+high["temperature_k"])/2
        for key, prop in props.items():
            direct = PropsSI(prop, "T", temperature, "P", 101325, "HEOS::Water")
            assert abs((low[key]+high[key])/2-direct)/abs(direct) < .001
        cp_from_h = (high["h_j_kg"]-low["h_j_kg"])/(high["temperature_k"]-low["temperature_k"])
        assert cp_from_h == pytest.approx(PropsSI("Cpmass", "T", temperature, "P", 101325, "HEOS::Water"), rel=.001)
