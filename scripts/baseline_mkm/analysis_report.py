"""Human-readable projection of the versioned analysis document."""

from html import escape
import json


def cell(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.9g}"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers, rows):
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(cell(v) for v in row) + " |" for row in rows],
    ]


def markdown(a):
    lines = [f"# MKM analysis · {a['project_id']}", "", f"Network `{a['network_version']}`", ""]
    if a["status"] != "analyzed":
        lines.extend(["## Kinetic evidence required", "", a["missing"]["result"], ""])
        for rid, gaps in a["missing"]["reactions"].items():
            lines.extend([f"### {rid}", "", *["- " + s for s in gaps], ""])
        lines.extend(["## Structural inspection", ""])
        for e in a["pathways"]["reactions"]:
            lines.append(
                f"- {e['reaction_id']} · {cell(e['direction']['forward']['reactants'])} → {cell(e['direction']['forward']['products'])}. Reversibility {cell(e['reversible'])}."
            )
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            f"{a['scope']} · {a['temperature_K']} K · partial pressures in bar {cell(a['partial_pressures_bar'])}",
            "",
            "## Surface coverage",
            "",
        ]
    )
    if a["format"] == "mkm-kinetic-analysis/2":
        lines += table(
            ["Species", "Molecules per reference", "Reference", "Site multiplicities", "Missing evidence"],
            [(r["species_id"], r["molecular_coverage"], r["molecular_reference"], r["site_occupancy"], r["missing"])
             for r in a["coverage"]],
        )
        lines += ["", "### Species contributions by inventory", ""]
        lines += table(
            ["Inventory", "Species", "Sites per molecule", "Occupied fraction"],
            [(site, sid, c["multiplicity"], c["occupied_fraction"])
             for site, item in a["utilization"].items() for sid, c in item["contributions"].items()],
        )
    else:
        lines += table(
            [
                "Species",
                "Phase",
                "Surface",
                "Site / type",
                "Multiplicity",
                "Species fraction",
                "Occupied fraction",
                "Fraction of all sites",
                "mol/m² of surface",
            ],
            [
                (
                    r["species_id"],
                    r["phase_id"],
                    r["surface_id"],
                    r["site_id"] + " / " + r["site_type"],
                    r["occupancy_multiplicity"],
                    r["species_coverage"],
                    r["occupied_fraction"],
                    r["fraction_of_all_sites"],
                    r["concentration_mol_per_surface_m2"],
                )
                for r in a["coverage"]
            ],
        )
    lines += ["", "## Site utilization", ""]
    lines += table(
        [
            "Site",
            "Catalyst phase",
            "Occupied",
            "Vacant",
            "Balance residual",
            "Competitors by occupancy",
            "Dominant",
        ],
        [
            (
                k,
                v["phase_id"],
                v["occupied_fraction"],
                v["vacancy_fraction"],
                v["balance_residual"],
                v["coverage_ranking"],
                v["dominant_adsorbates"],
            )
            for k, v in a["utilization"].items()
        ],
    )
    lines += [
        "",
        "## Elementary rates",
        "",
        f"Directional and net flux units are {a['rates']['reactions'][0]['flux_unit']}.",
        "",
    ]
    lines += table(
        [
            "Reaction",
            "kf (unit)",
            "kr (unit)",
            "Forward flux",
            "Reverse flux",
            "Net flux",
            "ΔG (eV)",
            "ΔG‡ f / r (eV)",
            "Near equilibrium",
        ],
        [
            (
                r["reaction_id"],
                f"{cell(r['kf'])} ({r['forward_unit']})",
                f"{cell(r['kr'])} ({cell(r['reverse_unit'])})",
                r["forward_flux"],
                r["reverse_flux"],
                r["net_flux"],
                r["reaction_free_energy_eV"],
                f"{cell(r['forward_activation_free_energy_eV'])} / {cell(r['reverse_activation_free_energy_eV'])}",
                r["near_equilibrium"],
            )
            for r in a["rates"]["reactions"]
        ],
    )
    lines += [
        "",
        "## Turnover and product distribution",
        "",
        f"Reference basis: {cell(a['tof']['reference_basis'])}. Signed gas stoichiometry: {cell(a['tof']['overall_stoichiometry'])}.",
        "",
    ]
    lines += table(
        ["Rate", "Per reference/s", "Per site/s", "Per pair/s", "mol/(m² s)", "mol/(kg s)", "mol/(m³ reactor s)"],
        [
            (
                k,
                v["per_reference_s"],
                v["per_site_s"],
                v["per_site_pair_s"],
                v["mol_per_m2_s"],
                v["mol_per_kg_s"],
                v["mol_per_m3_reactor_s"],
            )
            for k, v in [("Overall turnover", a["tof"]["overall"]), *a["tof"]["products"].items()]
        ],
    )
    lines += [
        "",
        f"Molar selectivity within the declared product set: {cell(a['selectivity']['molar'])}.",
        f"Element selectivity: {cell(a['selectivity']['element_selectivity'])}.",
        f"Net gas production: {cell(a['rates']['gas_net_production'])}.",
        f"Byproducts: {cell(a['selectivity']['byproduct_production'])}. Unconverted feed: {cell(a['selectivity']['unconverted_feed_outlet_per_reference_s'])}.",
        "",
        "## Pathway graph",
        "",
        a["pathways"]["algorithm"],
        "",
    ]
    for group in a["pathways"]["feed_to_product"]:
        lines.append(
            f"- {group['feed']} → {group['product']}: "
            + ", ".join(
                " → ".join(s["reaction_id"] + " (" + s["direction"] + ")" for s in path["steps"])
                for path in group["paths"]
            )
        )
    lines += [
        "",
        f"Cross-phase reaction contexts: {cell(a['pathways']['cross_phase_reactions'])}.",
        f"Mutually reachable components: {cell(a['pathways']['cyclic_species_components'])}.",
        "",
        "## Scientific validation",
        "",
        f"Status: {a['validation']['status']}. Reconstructed maximum surface residual: {cell(a['rates']['steady_state_residual'])}.",
        f"Element balances: {cell(a['selectivity']['element_balance'])}.",
        "Missing quantities are marked —. Machine-readable activity factors, gas source terms, inventory-specific rankings and graph edges are in [analysis.json](analysis.json).",
    ]
    return "\n".join(lines) + "\n"


def pathway_diagram(a):
    """One reaction node per stoichiometric event. A shared reaction node joins all co-reactants."""
    graph = a["pathways"]
    ids = {s: f"s{i}" for i, s in enumerate(graph["nodes"])}
    lines = [
        "# Reaction network",
        "",
        "Edges carry stoichiometric coefficients. Bidirectional arrows denote confirmed reversibility. Each reaction node joins all participants in that event.",
        "",
        "```mermaid",
        "flowchart LR",
    ]
    for sid, node in graph["nodes"].items():
        label = escape(sid + " · " + node["phase"])
        lines.append(f'    {ids[sid]}["{label}"]')
    for i, edge in enumerate(graph["reactions"]):
        rid = f"r{i}"
        direction = edge["direction"]["status"]
        label = escape(edge["reaction_id"] + " · " + direction)
        lines.append(f'    {rid}{{"{label}"}}')
        arrow = "<-->" if edge["reversible"] is True else "-->"
        side = edge["direction"]["forward"]
        for sid, coefficient in side["reactants"].items():
            lines.append(f"    {ids[sid]} {arrow}|{coefficient}| {rid}")
        for sid, coefficient in side["products"].items():
            lines.append(f"    {rid} {arrow}|{coefficient}| {ids[sid]}")
    return "\n".join([*lines, "```", ""])
