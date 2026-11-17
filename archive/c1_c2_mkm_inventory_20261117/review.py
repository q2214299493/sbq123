"""Read-only, source-bound refresh of an inventory; never an executable MKM."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import math
import sqlite3

from ase.io import read

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "outputs/c1_c2_mkm_inventory_20261117_v1"
PREVIOUS = ROOT / "outputs/c1_c2_mkm_inventory_20261116/inventory.json"
CHCO = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"
HYDROGEN = ROOT / "calculations/fe110_c2ho_h_to_c2h2o_ts_20260822"
R06 = HYDROGEN / "h_is_a_int06_dimer_neb9808511_image05_32r_16pn_20261004"
CONVENTION = "fe110_converged_toten_sigma0p20_v1"
VALIDATIONS = {
    "R05": "fe110_ch_co_dimer9998592_vfa2260_grade_a_20261115",
    "R07": "fe110_int06_mid_ci9796856_vfa9798421_grade_a",
}


def binding(path):
    return {"path": str(path), "sha256": sha256_file(path)}


def file_check(row):
    path = Path(row["local_path"]) if row["local_path"] else None
    exists = bool(path and path.is_file())
    return {"file_id": row["file_id"], "local_path": row["local_path"],
            "registered_sha256": row["sha256"], "exists": exists,
            "hash_matches": sha256_file(path) == row["sha256"] if exists else False}


def geometry(path):
    if not path.is_file():
        return {"path": str(path), "exists": False}
    atoms = read(path, format="vasp")
    counts = dict(Counter(atoms.get_chemical_symbols()))
    return {**binding(path), "exists": True, "atom_counts": counts,
            "identity_scope": "same-index source geometry;not a new site or stability review"}


def result_record(connection, result_id):
    row = connection.execute("SELECT * FROM results WHERE result_id=?", [result_id]).fetchone()
    if row is None:
        raise ValueError(f"Missing registered result: {result_id}")
    result = dict(row)
    source = dict(connection.execute("SELECT * FROM files WHERE file_id=?", [row["source_file_id"]]).fetchone())
    result["source_check"] = file_check(source)
    result["structure"] = geometry(Path(source["local_path"]).with_name("CONTCAR"))
    return result


def refresh_rows(previous, barriers):
    by_id = {row["barrier_set_id"]: row for row in barriers}
    rows = [dict(row) for row in previous["rows"]]
    for row in rows:
        barrier = by_id.get(row["barrier_set_id"])
        if barrier:
            for key in ("forward_barrier_ev", "reverse_barrier_ev", "reaction_energy_ev"):
                row[key] = barrier[key]
            row["evidence_status"] = "REGISTERED_ELECTRONIC_BARRIER_ONLY"
        else:
            row["evidence_status"] = "PARAMETERS_OR_STATE_INTERFACE_NEED_REVIEW"
        row["formal_kinetics_input"] = False
    r06 = next(row for row in rows if row["step_id"] == "R06")
    r06.update({"selected_structures": "IS-A9725473；Dimer9833429；INT069748648",
        "evidence": "已定位Dimer归档；最大原子力通过；最终方向审核仍needs_review；未检出对应Grade-A频率登记",
        "missing_parameters": "最终方向/软残差审核、局部频率验证及正式TS验收；之后兼容能垒和热校正",
        "next_action": "先复核现有9833429资料，不默认重跑NEB或Dimer",
        "evidence_status": "ARCHIVED_DIMER_NOT_REGISTERED_GRADE_A"})
    for step in ("R05", "R07"):
        next(row for row in rows if row["step_id"] == step)["evidence_status"] = "GRADE_A_TS_BARRIER_NOT_REGISTERED"
    return rows


def markdown(data):
    rows = data["rows"]
    lines = ["# Fe(110) C₁→C₂ 微观动力学盘点（2026-11-17）", "",
        "状态：缺口审核稿，不是已批准网络、自由能表或可执行MKM。数据库只读；未提交任何计算。", "",
        "## 已有电子能垒", "",
        "均为兼容 SIGMA=0.20 eV 最终 OUTCAR TOTEN；单位eV，不含ZPE、熵或自由能校正。", "",
        "| 步骤 | 选用IS / TS / FS作业 | 正向 | 反向 | 反应能 |",
        "|---|---|---:|---:|---:|"]
    jobs = {"R03": "9558184 / 9656664 / 9622455", "R04": "9715450(A) / 9720181 / 9573951",
        "R08": "9737143(MID) / 9746548 / 9725471(FS-A)", "R09": "9701350(A) / 9709074 / 9622444"}
    for row in rows:
        if row.get("forward_barrier_ev") is not None:
            lines.append(f"| {row['chemical_change']} | {jobs[row['step_id']]} | {row['forward_barrier_ev']:.6f} | "
                f"{row['reverse_barrier_ev']:.6f} | {row['reaction_energy_ev']:.6f} |")
    lines += ["", "A是反应就位端点，不能把相对A的势垒直接当作相对最低能参考态的势垒。", "",
        "## 不是缺少TS、但仍有登记/验证缺口的步骤", "",
        "| 步骤 | 已有证据 | 还缺什么 |", "|---|---|---|"]
    for step in ("R05", "R06", "R07"):
        row = next(row for row in rows if row["step_id"] == step)
        lines.append(f"| {row['chemical_change']}；{row['selected_structures']} | {row['evidence']} | {row['missing_parameters']} |")
    lines += ["", "9833429归档最大原子力0.015998 eV/Å、负曲率；final_mode_review仍needs_review，"
        "DIMCAR残差未据此自动接受。未检出Grade-A登记不等于证明从未算过频率。", "",
        "## 状态不能直接拼接", "",
        "- CO解离FS是C+O共吸附；C+H→CH的IS不含该旁观O。需审查氧库/共吸附相互作用，而不是直接相减不同组成的总能。",
        "- 单独CH*与CO*的能量之和不能替代CH+CO共吸附IS9839757。反应对形成、位点几率及共吸附能需要统一。",
        "- 偶联FS9842136是C₂HO*；加氢IS-A9725473是C₂HO*+H*。必须审核H来源、位点/构型及参考能转换。",
        "- 加氢阶段按IS-A→INT06→MID→FS-A分三段；H迁移和O–H成键不能合成一个已知势垒。",
        "- 多齿吸附的位点占用数尚未批准；方程为化学变化示意，不能用一个*或***替代位点守恒审核。", "",
        "C→CH的已登记FS电子能目录有OUTCAR、无CONTCAR。其既有能垒来源哈希与算术检查通过；"
        "本次未用POSCAR冒充最终结构，需另定位/核对9573951的最终结构关联后再做热校正。这不是判定需要重算。", "",
        "## 逐步缺口表", "", "| 编号 | 化学变化 | 已选结构/证据 | 缺失参数 |", "|---|---|---|---|"]
    for row in rows:
        lines.append(f"| {row['step_id']} | {row['chemical_change']} | {row['selected_structures']}；{row['evidence']} | {row['missing_parameters']} |")
    lines += ["", "## 按顺序推进，避免不必要重算", "",
        "1. 先审核并准备CH+CO与INT06→MID的兼容IS/TS/FS电子能垒登记。TS9998592与CI9796856不默认重算；正式报告仍需各自执行门。",
        "2. 对9833429补最终方向和软残差审核，再决定局部频率验证；没有凭归档力值宣布正式TS通过。",
        "3. 对选用IS/TS/FS准备一致局部活性集的热校正清单；已有TS频率先核验复用，稳定态缺失才补算。排除唯一反应坐标虚频，不静默处理额外软模。",
        "4. 审核反应对/位点/旁观物接口并固定温度、标准态、分压或条件覆盖度。没有实际自由能和前因子前只可标注电子能垒近似。",
        "5. 首版可限于可逆CH+CO反应对的瞬态或给定覆盖度条件模型。要CO/H₂进料的稳态TOF，另需H₂供氢、O→OH→H₂O排氧、水释放以及真实产物脱附/继续转化边界。",
        "", "H₂解离、O+H→OH、OH+H→H₂O：本次已接受能垒表未检出，先查历史端点/证据，再确定新增TS；"
        "CO/水/产品吸脱附不一律要求额外鞍点，须有可追溯的可逆速率模型。CH→CH₂只是竞争支路，不能据此报告CH₄选择性。", "",
        "## 软件、工况与后续范围", "",
        "项目首选CATKINAS/现有MATLAB入口；本轮未运行软件或求解MKM。示例能运行不代表Fe(110)输入已验证。",
        "温度、分压、初始覆盖度、位点密度、标准态及低频处理仍待审核；旧文档中的573 K等只是探索建议，未当成正式工况。",
        "覆盖度自洽/横向相互作用留作基线模型后的敏感性检查，不将其他催化剂论文参数导入本地能量。C₃及更长链不属于本次C₁→C₂最小盘点。", "",
        "## 验证范围", "",
        f"本次核验{len(data['registered_barriers'])}套登记能垒及12个电子能来源；"
        "正反能垒/反应能代数关系与来源哈希检查见verification.json。"
        "未重新进行TS科学验收、频率解析、位点守恒批准或求解速率。未检出热校正只指已登记结果名检索，不证明原始数据不存在。", ""]
    return "\n".join(lines)


def main():
    if OUTPUT.exists():
        raise ValueError("Refuse overwrite of existing inventory")
    previous = load_json_object(PREVIOUS)
    database = ROOT / "data/project_registry.sqlite3"
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        barriers = [dict(row) for row in connection.execute("SELECT * FROM ts_barriers WHERE validation_status='accepted'")]
        validations = [dict(row) for row in connection.execute("SELECT * FROM ts_validations WHERE grade='A' AND kinetic_eligible=1")]
        results = {rid: result_record(connection, rid) for b in barriers for rid in
            (b["initial_result_id"], b["ts_result_id"], b["final_result_id"])}
        contract_path = CHCO / "local_triplet_review_20261112_v1/reaction_contract.reviewed.json"
        contract = load_json_object(contract_path)
        endpoints = {key: result_record(connection, value["static_result_id"]) for key, value in contract["endpoints"].items()}
        pending_files = [dict(row) for row in connection.execute(
            "SELECT * FROM files WHERE file_id IN (?,?)", [
                "fe110_ch_co_dimer_20261112_job9998592__vfa20261115_010",
                "fe110_ch_co_dimer_20261112_job9998592__vfa20261115_011"])]
        thermo = [dict(row) for row in connection.execute("SELECT result_id,result_name,validation_status FROM results "
            "WHERE lower(result_name) LIKE '%free_energy%' OR lower(result_name) LIKE '%gibbs%' "
            "OR lower(result_name) LIKE '%zpe%' OR lower(result_name) LIKE '%entropy%'")]
        schema = connection.execute("SELECT value FROM schema_metadata WHERE key='schema_version'").fetchone()[0]
        connection.rollback()
    finally:
        connection.close()
    checks = []
    for b in barriers:
        is_, ts, fs = [results[b[k]] for k in ("initial_result_id", "ts_result_id", "final_result_id")]
        expected = (ts["numeric_value"]-is_["numeric_value"], ts["numeric_value"]-fs["numeric_value"], fs["numeric_value"]-is_["numeric_value"])
        values = tuple(b[k] for k in ("forward_barrier_ev", "reverse_barrier_ev", "reaction_energy_ev"))
        checks.append({"barrier_set_id": b["barrier_set_id"], "arithmetic_matches": all(
            math.isfinite(v) and abs(v-w) < 1e-10 for v, w in zip(values, expected, strict=True)),
            "convention_matches": b["energy_convention"] == CONVENTION and all(x["reference_convention"] == CONVENTION for x in (is_, ts, fs)),
            "source_hashes_match": all(x["source_check"]["hash_matches"] for x in (is_, ts, fs)),
            "composition_matches": all(x["structure"]["atom_counts"] == is_["structure"]["atom_counts"] for x in (ts, fs))
                if all(x["structure"]["exists"] for x in (is_, ts, fs)) else None})
    if len(barriers) != 4 or not all(
            row["arithmetic_matches"] and row["convention_matches"] and row["source_hashes_match"]
            and row["composition_matches"] is not False for row in checks):
        raise ValueError(f"Registered inventory consistency check failed: {checks}")
    if not all(any(v["ts_validation_id"] == key for v in validations) for key in VALIDATIONS.values()):
        raise ValueError("Expected Grade-A source no longer registered")
    if any(v["source_saddle_calculation_id"] == "fe110_is_a_int06_dimer_9833429" for v in validations):
        raise ValueError("R06 eligibility changed;review inventory classification before refreshing")
    analysis = load_json_object(R06 / "dimer_analysis.json")
    mode_review = load_json_object(R06 / "final_mode_review.json")
    data = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "DRAFT_FOR_NETWORK_REVIEW_NOT_EXECUTABLE_MKM", "source_registry": str(database),
        "registry_schema": schema, "registry_read_only": True, "previous_inventory": binding(PREVIOUS),
        "rows": refresh_rows(previous, barriers), "registered_barriers": barriers,
        "registered_grade_a_validations": validations, "registered_energy_members": results,
        "chco_pending_barrier": {"contract": binding(contract_path), "endpoints": endpoints,
            "source_checks": [file_check(row) for row in pending_files], "ts_validation_id": VALIDATIONS["R05"],
            "unregistered_barrier_value_reported": False},
        "r06_archived_candidate": {"analysis": binding(R06 / "dimer_analysis.json"),
            "status": analysis["status"], "final_atomic_force_max_eVA": analysis["final_atomic_force_max_eVA"],
            "final_curvature_eVA2": analysis["final_curvature_eVA2"], "mode_review": binding(R06 / "final_mode_review.json"),
            "mode_review_status": mode_review["status"], "ts_validation_registered": False,
            "raw_source_hash_checks": [{"path": r["path"], "hash_matches": sha256_file(Path(r["path"])) == r["sha256"]}
                for r in analysis["source_files"]]},
        "thermo_registered_name_matches": thermo,
        "thermo_search_limit": "Registry result-name search only;not absence of raw modes/unregistered corrections",
        "formal_kinetics_ready": False, "scientific_execution": {"new_vasp": False, "new_gpu": False,
            "new_training": False, "mkm_run": False, "registry_write": False}}
    OUTPUT.mkdir(parents=True)
    write_json_exclusive(OUTPUT / "inventory.json", data)
    (OUTPUT / "C1-C2能垒与补算清单.md").write_text(markdown(data), encoding="utf-8")
    write_json_exclusive(OUTPUT / "verification.json", {"status": "PASS", "scope": "inventory arithmetic/source checks only",
        "registered_barrier_checks": checks, "review_rows": len(data["rows"]), "registry_read_only": True,
        "formal_kinetics_ready": False, "inventory_sha256": sha256_file(OUTPUT / "inventory.json")})
    print({"registered_barriers": len(barriers), "grade_a": len(validations), "rows": len(data["rows"]), "formal_kinetics_ready": False})


if __name__ == "__main__":
    main()
