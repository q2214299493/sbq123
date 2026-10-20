"""Bounded CPU geometry verification and task documentation; never executes a model."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys

import jsonschema
import numpy as np

from scripts.adsorption.build_fe110_adsorption import Poscar, expanded_symbols, read_poscar
from scripts.adsorption.build_fe110_care_isomers import equivalent_pose_rmsd, surface_pose_symmetries


ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "calculations/fe110_c2_adsorption_11_15_20261020"
OUTPUT = TASK / "candidates_v3"
REQUEST = ROOT / "configs/adsmind_lite/fe110_c2_11_15_exploratory_20261020.json"
STAMP = datetime.now(timezone(timedelta(hours=8))).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def mol_signature(path):
    """Read this source's V3000 C/O graph and explicit valence declarations."""
    atoms, bonds = {}, []
    section = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "BEGIN ATOM" in line:
            section = "atom"
        elif "BEGIN BOND" in line:
            section = "bond"
        elif "END ATOM" in line or "END BOND" in line:
            section = None
        elif line.startswith("M  V30 ") and section:
            fields = line.split()[2:]
            if section == "atom":
                symbol = fields[1]
                match = re.search(r"\bVAL=(\d+)", line)
                atoms[int(fields[0])] = (symbol, int(match[1]) if match else {"C": 4, "O": 2}[symbol])
            else:
                bonds.append(tuple(map(int, fields[1:4])))
    assert atoms and bonds, "unexpected molecule serialization"
    result = []
    for index, (symbol, valence) in atoms.items():
        adjacent = [(order, second if first == index else first)
                    for order, first, second in bonds if index in (first, second)]
        hydrogens = valence - sum(order for order, _ in adjacent)
        assert hydrogens >= 0
        result.append([symbol, hydrogens, sorted(atoms[other][0] for _, other in adjacent)])
    return sorted(result)


def geometry_record(row, target, slab):
    path = OUTPUT / row["structure"]
    pose = read_poscar(path)
    symbols = expanded_symbols(pose)
    cart = pose.frac @ pose.cell
    ads = list(range(45, len(symbols)))
    shifts = np.array([[x, y, 0.] for x, y in itertools.product((-1, 0, 1), repeat=2)]) @ pose.cell

    def distance(first, second):
        return float(np.min(np.linalg.norm(cart[second] - cart[first] + shifts, axis=1)))

    radii = {"C": .76, "O": .66, "H": .31}
    edges = {(first, second) for first, second in itertools.combinations(ads, 2)
             if distance(first, second) <= 1.25 * (radii[symbols[first]] + radii[symbols[second]])}
    signature = []
    for index in ads:
        neighbors = [second if first == index else first for first, second in edges if index in (first, second)]
        if symbols[index] == "H":
            assert len(neighbors) == 1 and symbols[neighbors[0]] != "H"
        else:
            signature.append([symbols[index], sum(symbols[other] == "H" for other in neighbors),
                              sorted(symbols[other] for other in neighbors if symbols[other] != "H")])
    nearest = {index: min((distance(index, iron), iron + 1) for iron in range(45)) for index in ads}
    nonbonded = [(distance(first, second), first + 1, second + 1)
                 for first, second in itertools.combinations(range(len(symbols)), 2)
                 if second >= 45 and (first, second) not in edges]
    minimum_contact = min(nonbonded)
    counts = Counter(symbols[45:])
    expected_counts = Counter({element: int(count or 1) for element, count in re.findall(r"([A-Z][a-z]?)(\d*)", target["formula"])})
    checks = {
        "file_hash": digest(path) == row["structure_sha256"],
        "composition": counts == expected_counts,
        "exact_graph_and_H_placement": sorted(signature) == target["signature"],
        "source_molecule_graph": sorted(signature) == mol_signature(OUTPUT / "originals" / target["id"] / "source_molecule.mol"),
        "slab_cell_and_coordinates": np.array_equal(pose.cell, slab.cell) and np.array_equal(pose.frac[:45], slab.frac),
        "fixed_layers_and_mobile_adsorbate": pose.flags[:45] == slab.flags and all(flags == ("T", "T", "T") for flags in pose.flags[45:]),
        "finite": bool(np.isfinite(pose.frac).all()),
        "minimum_nonbonded_at_least_1A": minimum_contact[0] >= 1.,
        "heavy_Fe_contact": min(nearest[i][0] for i in ads if symbols[i] != "H") >= 1.65,
        "H_Fe_contact": min(nearest[i][0] for i in ads if symbols[i] == "H") >= 1.35,
        "molecule_attached": any(nearest[i][0] <= 2.65 for i in ads if symbols[i] != "H"),
        "above_top_surface": min(cart[i, 2] for i in ads) - max(cart[:45, 2]) >= 1.35,
        "builder_geometry_and_warnings": row["geometry_review"]["verdict"] == "pass" and not row["geometry_review"]["warnings"],
    }
    checks = {key: bool(value) for key, value in checks.items()}
    assert all(checks.values()), (row["name"], checks)
    carbon = [i for i in ads if symbols[i] == "C"]
    oxygen = [i for i in ads if symbols[i] == "O"]
    return pose, {
        "name": row["name"], "verdict": "PASS_INITIAL_GEOMETRY_ONLY", "checks": checks,
        "C_O_bonds_A": [distance(a, b) for a, b in sorted(edges) if {symbols[a], symbols[b]} == {"C", "O"}],
        "nearest_C_Fe": [{"C_index_1based": i + 1, "distance_A": nearest[i][0], "Fe_index_1based": nearest[i][1]} for i in carbon],
        "nearest_O_Fe": [{"O_index_1based": i + 1, "distance_A": nearest[i][0], "Fe_index_1based": nearest[i][1]} for i in oxygen],
        "C_union_support_Fe_1based_at_2p65A": sorted({j + 1 for i in carbon for j in range(45) if distance(i, j) <= 2.65}),
        "minimum_nonbonded_contact_A": minimum_contact[0],
    }


def main():
    if (TASK / "initial_geometry_verification.json").exists():
        raise FileExistsError("preserve the verification receipt")
    request = json.loads(REQUEST.read_text(encoding="utf-8"))
    manifest = json.loads((OUTPUT / "candidate_review.json").read_text(encoding="utf-8"))
    slab = read_poscar(ROOT / manifest["source_slab"])
    targets = {target["id"]: target for target in request["targets"]}
    assert len(manifest["candidates"]) == 15
    assert Counter(row["species_id"] for row in manifest["candidates"]) == Counter({key: 3 for key in targets})
    poses, rows = {}, []
    for row in manifest["candidates"]:
        pose, result = geometry_record(row, targets[row["species_id"]], slab)
        poses[row["name"]] = pose
        rows.append(result)
    operations = surface_pose_symmetries(slab)
    pairs = []
    for species in targets:
        names = sorted(name for name in poses if name.startswith(species + "_"))
        for first, second in itertools.combinations(names, 2):
            reference, other = poses[first], poses[second]
            comparisons = [other]
            if species == "15":
                coords = other.frac.copy()
                coords[[45, 46]] = coords[[46, 45]]
                comparisons.append(Poscar(other.comment, other.cell, other.symbols, other.counts, coords, other.flags))
            value = min(equivalent_pose_rmsd(reference, item, operations) for item in comparisons)
            assert value > .20
            pairs.append({"pair": [first, second], "RMSD_A": value, "equivalent_C_swap_checked": species == "15"})
    save(TASK / "initial_geometry_verification.json", {"status": "PASS_INITIAL_GEOMETRY_ONLY", "scientific_acceptance": False,
         "checked_at": STAMP, "candidates": rows, "seed_deduplication": pairs,
         "minimum_pair_RMSD_A": min(item["RMSD_A"] for item in pairs),
         "unverified": ["relaxed stability", "energies", "convergence", "global minimum", "model execution readiness"]})

    image_query = {
        "image_path": "C:/Users/86177/AppData/Local/Temp/codex-clipboard-7420e324-14aa-4c36-b9f1-d0108f0314cf.png",
        "visible_features": ["Rows 11-15 contain five formulas, five connectivity strings and CARE identity prefixes.",
                             "Rows 12-14 share formula C2H3O but show different C-C-O, C-C-OH and C-O-C connections.",
                             "No surface, adsorption site, geometry, bond length or energy is displayed."],
        "interpretations": [{"claim": "Use the existing active true Fe(110) Fe45 branch.", "confidence": "high", "basis": "Repository active branch; not inferred from the image."},
                            {"claim": "Prepare three starting structures for each of the five exact identities.", "confidence": "high", "basis": "User request combined with the visible five rows."}],
        "query_text": "Fe(110) ethylidyne CCH3, acetyl CH3CO, CH2COH, methoxycarbyne COCH3, ethylene C2H4 stable adsorption geometries for initial candidate construction",
        "review_status": "reviewed",
    }
    schema = json.loads((ROOT / "skills/catalysis-data-retrieval/references/image_query_schema.json").read_text())
    jsonschema.validate(image_query, schema)
    save(TASK / "retrieval/image_query.json", image_query)
    save(TASK / "retrieval/whitelist_search.json", {
        "searched_at": STAMP, "status": "NO_WHITELIST_MATCH", "scope": "bounded domain-restricted indexed search, not an exhaustive database census",
        "queries": ["Fe(110) ethylidyne acetyl ethylene adsorption", "Fe(110) CH2COH adsorption", "Fe(110) COCH3 adsorption", "Fe(110) CH3CO CCH3 adsorption structure"],
        "domains": ["catalysis-hub.org", "catappdatabase.org", "opencatalystproject.org", "fair-chem.github.io", "archive.materialscloud.org", "materialsproject.org", "iochem-bd.org", "nomad-lab.eu"],
        "usable_records": 0, "result": "The four recorded queries returned no indexed results.",
        "limitation": "This cannot establish that every underlying database lacks relevant structures."})
    (TASK / "retrieval/records.jsonl").touch(exist_ok=False)
    save(TASK / "retrieval/retrieval_top5.json", {"status": "NO_WHITELIST_MATCH", "results": [],
         "production_ready": False, "scientific_acceptance": False,
         "BM25_score": None, "semantic_score": None, "hybrid_score": None,
         "ranking_status": "NOT_RUN_NO_USABLE_RECORDS", "next_stage": "controlled primary-literature review; user-authorized local hypothesis construction"})
    literature = [
        {"id": "Erley1982", "doi": "10.1016/0039-6028(82)90151-0", "journal": "Surface Science",
         "publisher_url": "https://www.sciencedirect.com/science/article/pii/0039602882901510",
         "title": "Vibrational spectra of acetylene and ethylene adsorbed on Fe(110)",
         "supports": "Molecular ethylene on Fe(110) at 120 K; EELS favors triangular mu3 adsorption and a trans-twisted molecular conformation.",
         "limit": "Abstract accessible through indexed publisher content; full-text open failed. No numerical twist angle or coordinates recovered. 15_A has three Fe contacts but does not reconstruct the trans-twisted geometry."},
        {"id": "Li2018", "doi": "10.1021/acs.jpcc.8b10310", "journal": "Journal of Physical Chemistry C",
         "publisher_url": "https://pubs.acs.org/doi/abs/10.1021/acs.jpcc.8b10310",
         "title": "Successive Dissociation of CO, CH4, C2H6, and CH3CHO on Fe(110): Retrosynthetic Understanding of FTS Mechanism",
         "supports": "Fe(110) calculations include acetyl CH3CO and ethylene C2H4.",
         "limit": "Publisher abstract and SI description indexed; direct full text/SI access failed. Different cell/coverage; no transferable coordinates obtained."},
        {"id": "Li2019", "doi": "10.1016/j.susc.2019.121456", "journal": "Surface Science",
         "publisher_url": "https://www.sciencedirect.com/science/article/pii/S0039602819302651",
         "title": "Mechanistic insight into CO activation, methanation and C-C bond formation from coverage dependent CO hydrogenation on Fe(110)",
         "supports": "The primary Fe(110) mechanism includes CH3CO and CH3C.",
         "limit": "High-coverage model; indexed publisher abstract only, direct open HTTP 403; no local site ranking or geometry copied."},
        {"id": "Purdy2020", "doi": "10.1039/D0SC00875C", "journal": "Chemical Science",
         "publisher_url": "https://pubs.rsc.org/en/content/articlehtml/2020/sc/d0sc00875c",
         "title": "Structural trends in the dehydrogenation selectivity of palladium alloys",
         "supports": "Contains a pure bcc Fe(110) comparison including ethylidyne.",
         "limit": "Alloy geometries cannot be transferred to bare Fe(110); the indexed Fe(110) supplement does not establish our hollow/bridge/top ordering."},
    ]
    for item in literature:
        item.update(retrieved_at=STAMP, claim_type="literature_claim", accepted_structure_transfer=False,
                    geometry_coordinates_recovered=False, energy_imported=False, DOI_identity_basis="DOI and title match the primary publisher record")
    save(TASK / "retrieval/literature_context.json", {"records": literature, "ranking_not_claimed": True,
         "exact_geometry_not_found_for": ["13 [CH2]-[C]-OH", "14 [C]-O-CH3"],
         "authority": "Qualitative context only; no fabricated human review or production evidence acceptance."})
    save(TASK / "preparation_notes.json", {
        "final_version": "candidates_v3", "status": "PREPARED_FOR_REVIEW_NOT_RELAXED",
        "preserved_local_versions": {"candidates_v1": "First geometry package; branch-wrapping defect in some plots.",
                                     "candidates_v2": "Plots fixed; superseded selection-exclusion bookkeeping clarified in v3."},
        "failed_preparation_attempts": ["An initial 11 anchor-index assumption targeted methyl carbon; exact graph audit corrected the anchor before any output was written.",
                                        "An initial 12 placement lowered atoms into the surface; hard geometry rejection occurred before output. Final negative carbonyl tilt and larger distance pass unchanged thresholds.",
                                        "RDKit is absent in the local environment; independent V3000 valence/bond parsing replaces that optional graph check.",
                                        "The first receipt serialization rejected a numpy boolean before data were written. The zero-byte verification.json is preserved; explicit Python booleans and serialize-before-open fix receipt writing."],
        "not_executed": ["GPU inference", "ML relaxation", "VASP", "energy extraction", "registry or Excel promotion"]})

    commands = [
        [sys.executable, "-m", "py_compile", "scripts/adsorption/build_fe110_care_batch.py", "tests/test_fe110_care_requested_seeds.py", str(Path(__file__).relative_to(ROOT))],
        [sys.executable, "-c", "import scripts.adsorption.build_fe110_care_batch"],
        [sys.executable, "-m", "ruff", "check", "scripts/adsorption/build_fe110_care_batch.py", "tests/test_fe110_care_requested_seeds.py", str(Path(__file__).relative_to(ROOT))],
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "tests/test_fe110_care_batch.py", "tests/test_fe110_care_requested_seeds.py"],
        [sys.executable, "skills/catalysis-data-retrieval/scripts/validate_records.py", str((TASK / "retrieval/records.jsonl").relative_to(ROOT))],
    ]
    receipts = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
        receipts.append({"command": command, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if result.returncode:
            save(TASK / "validation_commands_failed.json", receipts)
            raise RuntimeError(f"validation failed: {command}")
    save(TASK / "validation_commands.json", receipts)

    text = ["# Fe(110) 第 11–15 项：每种三套初始吸附构型", "", "已构建 15 个 POSCAR、五张三构型俯视/侧视图和数值几何表。全部通过初始几何检查；零次模型调用、零次计算提交。",
            "", "这些是待弛豫候选。A/B/C 表示本次准备顺序，不代表能量排名；没有把任何候选称为已证明的最稳态。", "", "## 物种与候选", "",
            "| 项目 | 精确连接 | A | B | C |", "|---|---|---|---|---|"]
    for target in request["targets"]:
        links = [f"[{target['id']}_{letter}：{recipe['label']}]({target['id']}_{letter}/POSCAR)" for letter, recipe in zip("ABC", target["seed_recipes"], strict=True)]
        text.append(f"| {target['id']} {target['formula']} | `{target['connectivity']}` | " + " | ".join(links) + " |")
    text += ["", "11：C 端三 Fe 空位、双 Fe 长桥及单 Fe 顶位。12：保留 CH3 的 C/O 双中心三种排列。13：保持 OH 上的 H，使用三种链/OH 排列。14：保持 C–O–C，改变无 H 端 C 的配位。15：三 Fe 多中心假说、既有双 C 单 Fe 近邻姿态和短桥方向姿态。", "",
             "## 文献依据与适用边界", "", "先做白名单有界检索：未得到可用精确结构记录。空记录校验通过不等于生产检索通过；未执行 BM25/语义排序。检索范围和访问限制保存在 retrieval/。", ""]
    for item in literature:
        text.append(f"- [{item['title']}]({item['publisher_url']})，DOI `{item['doi']}`：{item['supports']} {item['limit']}")
    text += ["", "未获取每种三套最低能坐标。13、14 未找到本次裸 Fe(110) 精确图的可用结构证据；按用户本轮授权使用既有 CARE 局部模板及合理锚定假说。11 的空位/桥位比较同样属于构造假说。15_A 只借鉴多 Fe 配位线索，未复原文献 trans-twisted 构型，也未指定没有来源的扭转角。", "",
             "CARE 姿态和原始排序量属于模型预测来源；构造姿态不继承母姿态能量。外部及预测能量均未进入本地吸附能、注册表或 Excel。", "",
             "## 初始几何核验", "", "同一清洁 Fe45 晶胞及 Fe 坐标完全保留，底部 Fe1–18 固定，其余原子可动。独立 V3000 图核对和周期距离检查确认三种 C2H3O 未互换、OH 上的 H 未迁移。表中 Fe 原子编号从 1 开始，距离单位 Å。", "",
             "| 构型 | C–O 键 | 最近 C–Fe（Fe编号） | 最近 O–Fe（Fe编号） | 最小非键接触 | 判定 |", "|---|---|---|---|---|---|"]
    for row in rows:
        co = "/".join(f"{x:.3f}" for x in row["C_O_bonds_A"]) or "—"
        cf = "/".join(f"{x['distance_A']:.3f}(Fe{x['Fe_index_1based']})" for x in row["nearest_C_Fe"])
        of = "/".join(f"{x['distance_A']:.3f}(Fe{x['Fe_index_1based']})" for x in row["nearest_O_Fe"]) or "—"
        text.append(f"| {row['name']} | {co} | {cf} | {of} | {row['minimum_nonbonded_contact_A']:.3f} | 初始几何通过 |")
    text += ["", f"全部 15 项初始几何通过，当前规则软警告 0 项。同物种构型的最小对称去重 RMSD 为 {min(item['RMSD_A'] for item in pairs):.3f} Å，大于既有 0.20 Å 阈值；乙烯额外计入两个 C 的互换及相同 H 的排列。去除统一高度位移，未用单纯升降补数量。", "",
             "22 项相关测试、语法、导入和定向 Ruff 检查的实际输出见 ../validation_commands.json。独立核验结果见 ../initial_geometry_verification.json。原始预测姿态及未选用原因保存在 originals/ 和 candidate_review.json。", "",
             "## 结构图", ""]
    for species in targets:
        text += [f"### 第 {species} 项", "", f"![{species} 三种构型]({species}_structures.png)", ""]
    text += ["## 复现", "", "从 work 根目录运行，输出目录必须是新目录：", "", "```powershell",
             "python -m scripts.adsorption.build_fe110_care_batch --network C:/Users/86177/Desktop/app/CARE_Fe110_FT_C1_C6/evaluated_networks/ft_C2O1_Fe110_eval.pkl.json.gz --slab calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR --request configs/adsmind_lite/fe110_c2_11_15_exploratory_20261020.json --output calculations/fe110_c2_adsorption_11_15_20261020/reproduced_candidates",
             "```", "", "原网络和清洁 slab 的 SHA256 由请求文件固定，缺失时必须取回同一来源，不能换用同分子式结构。未验证弛豫稳定性、电子/力收敛、吸附能及全局最低能。下一步：审阅这些构型，再确定单独的预弛豫范围。", ""]
    with (OUTPUT / "structure_review.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(text))
    save(TASK / "artifact_hashes.json", {"created_at": STAMP, "canonical_candidate_directory": "candidates_v3",
         "files": [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": digest(path)}
                   for path in sorted(TASK.rglob("*")) if path.is_file() and path.name != "verification.json" and "candidates_v1" not in path.parts and "candidates_v2" not in path.parts]})
    print(f"verified=15 warnings=0 min_seed_RMSD={min(item['RMSD_A'] for item in pairs):.4f} commands={len(receipts)} all_exit_zero=True")


if __name__ == "__main__":
    main()
