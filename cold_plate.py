"""Reduced-order straight-channel cold plate. SI internally; see docs/cold-plate.md."""

from dataclasses import asdict, dataclass
from math import floor, isfinite, sqrt, tanh


@dataclass(frozen=True)
class ColdPlateDesign:
    width_mm: float = 0.3
    depth_mm: float = 1.2
    web_mm: float = 0.4
    base_mm: float = 1.0
    flow_lpm: float = 0.2
    conductivity_w_mk: float = 390.0


@dataclass(frozen=True)
class ColdPlateCase:
    name: str = "nominal"
    heat_w: float = 100.0
    inlet_c: float = 25.0  # At the plate inlet, after the external pump.
    max_base_c: float = 45.0
    max_pressure_pa: float = 20000.0
    max_pump_w: float = 0.5
    pump_efficiency: float = 0.4
    electricity_per_kwh: float = 0.15
    hours: float = 24.0
    length_mm: float = 100.0
    plate_width_mm: float = 50.0
    edge_mm: float = 1.0
    cover_mm: float = 1.0
    max_height_mm: float = 5.0
    min_feature_mm: float = 0.2
    max_depth_width_ratio: float = 6.0
    minor_loss_k: float = 2.0  # Assumed aggregate entrance/exit loss, not headers.
    heat_transfer_multiplier: float = 1.0  # Model-form sensitivity only.
    rho_kg_m3: float = 997.0
    mu_pa_s: float = 0.00089
    cp_j_kgk: float = 4181.0
    coolant_k_w_mk: float = 0.607


def _positive(value, name):
    if isinstance(value, bool) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def validate_case(case):
    for name, value in asdict(case).items():
        if name in ("name", "inlet_c", "max_base_c", "minor_loss_k", "electricity_per_kwh"):
            continue
        _positive(value, name)
    for name in ("inlet_c", "max_base_c", "minor_loss_k", "electricity_per_kwh"):
        if not isfinite(getattr(case, name)):
            raise ValueError(f"{name} must be finite")
    if not 0 < case.pump_efficiency <= 1 or case.minor_loss_k < 0 or case.electricity_per_kwh < 0:
        raise ValueError("Invalid efficiency, loss coefficient, or tariff")
    if case.max_base_c <= case.inlet_c or case.plate_width_mm <= 2 * case.edge_mm:
        raise ValueError("Invalid temperature limit or plate width")


def rectangular_correlations(aspect):
    """Return Darcy f*Re and three-heated-side fully developed Nu.

    aspect = width/depth in (0, 1]. Adiabatic cover spans width.
    No orientation swapping: the three-side thermal problem is not symmetric.
    """
    if not isfinite(aspect) or not 0 < aspect <= 1:
        raise ValueError("width/depth must be in (0, 1]")
    a = aspect
    po = 96 * (1 - 1.3553*a + 1.9467*a**2 - 1.7012*a**3 + 0.9564*a**4 - 0.2537*a**5)
    nu = 8.235 * (1 - 1.883*a + 3.767*a**2 - 5.814*a**3 + 5.361*a**4 - 2*a**5)
    return po, nu


def evaluate_design(case, design):
    """Return model diagnostics even when operating/domain constraints fail.

    Invalid numerical inputs raise. Geometrically invalid candidates have no
    fabricated physics outputs and are infeasible. Feasibility is model-only.
    """
    validate_case(case)
    for name, value in asdict(design).items():
        _positive(value, name)
    d, c = design, case
    reasons = []
    if min(d.width_mm, d.depth_mm, d.web_mm, d.base_mm,
           c.cover_mm, c.edge_mm) < c.min_feature_mm:
        reasons.append("minimum_feature")
    if not 1 <= d.depth_mm / d.width_mm <= c.max_depth_width_ratio:
        reasons.append("channel_aspect")
    if d.depth_mm + d.base_mm + c.cover_mm > c.max_height_mm:
        reasons.append("stack_height")
    available = c.plate_width_mm - 2*c.edge_mm
    count = floor((available + d.web_mm) / (d.width_mm + d.web_mm) + 1e-12)
    if count < 2:
        reasons.append("channel_count")
    result = {**asdict(d), "channel_count": count, "geometry_ok": not reasons,
              "domain_ok": False, "feasible": False, "violations": ";".join(reasons)}
    if reasons:
        return result

    w, depth, web, base, length = [v/1000 for v in
                                 (d.width_mm, d.depth_mm, d.web_mm, d.base_mm, c.length_mm)]
    flow = d.flow_lpm / 60000  # L/min -> m^3/s, total across all parallel channels.
    velocity = flow / (count*w*depth)
    dh = 2*w*depth/(w+depth)
    re = c.rho_kg_m3*velocity*dh/c.mu_pa_s
    pr = c.cp_j_kgk*c.mu_pa_s/c.coolant_k_w_mk
    po, nu = rectangular_correlations(w/depth)
    darcy = po/re
    dp_friction = darcy*length/dh*c.rho_kg_m3*velocity**2/2
    dp_minor = c.minor_loss_k*c.rho_kg_m3*velocity**2/2
    dp = dp_friction + dp_minor
    hydraulic = dp*flow
    pump = hydraulic/c.pump_efficiency
    h = nu*c.coolant_k_w_mk/dh*c.heat_transfer_multiplier
    mh = sqrt(2*h/(d.conductivity_w_mk*web))*depth
    fin_efficiency = tanh(mh)/mh
    area = count*length*(w + 2*fin_efficiency*depth)  # Adiabatic cover excluded.
    r_conv = 1/(h*area)
    r_base = base/(d.conductivity_w_mk*length*c.plate_width_mm/1000)
    capacity = c.rho_kg_m3*flow*c.cp_j_kgk
    # Pressure work dissipated inside plate becomes coolant heat. Motor losses
    # and the rest of the cooling loop are outside this inlet/outlet boundary.
    outlet = c.inlet_c + (c.heat_w + hydraulic)/capacity
    peak = outlet + c.heat_w*(r_conv+r_base)
    hydro_fraction = 0.05*re*dh/length
    thermal_fraction = 0.1*re*pr*dh/length
    domain_reasons = []
    if re > 2000:
        domain_reasons.append("nonlaminar")
    if hydro_fraction > 0.1:
        domain_reasons.append("hydrodynamic_entry")
    if thermal_fraction > 1:
        domain_reasons.append("thermal_entry_at_outlet")
    # Explicit approximation envelope for fixed room-temperature water properties.
    if c.inlet_c < 20 or outlet > 40:
        domain_reasons.append("constant_property_envelope")
    reasons.extend(domain_reasons)
    if peak > c.max_base_c:
        reasons.append("base_temperature")
    if dp > c.max_pressure_pa:
        reasons.append("pressure_drop")
    if pump > c.max_pump_w:
        reasons.append("pump_power")
    energy = pump*c.hours/1000
    result.update({
        "domain_ok": not domain_reasons, "feasible": not reasons,
        "violations": ";".join(reasons), "active_width_mm": count*d.width_mm+(count-1)*d.web_mm,
        "hydraulic_diameter_m": dh, "velocity_m_s": velocity, "reynolds": re, "prandtl": pr,
        "darcy_friction": darcy, "nusselt": nu, "h_w_m2k": h,
        "hydrodynamic_entry_fraction": hydro_fraction, "thermal_entry_fraction": thermal_fraction,
        "fin_efficiency": fin_efficiency, "effective_area_m2": area,
        "r_conduction_k_w": r_base, "r_convection_k_w": r_conv,
        "outlet_c": outlet, "peak_base_c": peak,
        "thermal_resistance_k_w": (peak-c.inlet_c)/c.heat_w,
        "friction_pressure_pa": dp_friction, "minor_pressure_pa": dp_minor,
        "pressure_pa": dp, "hydraulic_w": hydraulic, "pump_w": pump,
        "pump_kwh": energy, "pump_cost": energy*c.electricity_per_kwh,
        "heat_removed_kwh": c.heat_w*c.hours/1000,
    })
    return result
