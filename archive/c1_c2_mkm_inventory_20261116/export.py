"""Read-only registry inventory for a draft C1-C2 network,not kinetic inputs."""
from datetime import datetime, timezone
from pathlib import Path
import math

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from scripts.registry_connection import open_registry

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/c1_c2_mkm_inventory_20261116"
BASE = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109"

# Equations describe chemical changes only;site multiplicities remain unreviewed.
ROWS = [
    ["R01", "进料扩展", "CO(g) ⇄ CO*", "CO气相9733110；CO/top9558184", "参考态已登记", "吸附自由能、碰撞/黏附及脱附速率、位点定义", "先查现有参考和热校正，不默认新TS"],
    ["R02", "进料扩展", "H₂(g) ⇄ 2H*", "H₂气相9573527；H*及H+H端点待选", "本次已接受能垒表未检出此步", "H₂解离/复合速率、双位点占用；检索历史结果", "不能用一个H*吸附能替代解离能垒"],
    ["R03", "C1供给", "CO* ⇄ C* + O*", "IS9558184；TS9656664；FS9622455", "电子能垒已接受", "一致局部活性集热校正；O旁观物/后续去向", "保留C+O共吸附身份，不能接成无O的C态"],
    ["R04", "C1供给", "C* + H* ⇄ CH*", "IS-A9715450；TS9720181；FS9573951", "电子能垒已接受", "热校正；最低参考态到A的就位/迁移；共吸附参考转换", "复用A反应端点，不把相对A能垒当相对最低态"],
    ["R05", "局部核心", "CH* + CO* ⇄ [CH]–[C]–[O]*", "IS9839757重分类共吸附；TS9998592；FS9842136", "Grade A；VFA2260；正式能垒未登记", "兼容IS/TS/FS最终TOTEN登记；IS/FS局部频率与ΔG‡", "首先完成现有数据的兼容电子能垒核对，不重跑TS"],
    ["L01", "状态连接", "偶联产物 + H* 与加氢反应池对齐", "FS9842136；加氢IS-A9725473；最低参考IS-B待核", "非基元反应，不赋予速率常数", "构型/位点、H引入、旁观物和共吸附能参考对齐", "不能凭C₂HO分子式相同把两套状态直接合并"],
    ["R06", "加氢扩展", "IS-A ⇄ INT06（H*迁移）", "IS-A9725473；INT069748648；后续TS记录待定位", "未检出此段正式Grade-A登记，不等于未计算", "查后续Dimer/VFA归档、端点和能垒登记", "先查归档；不凭旧草案判定必须重算"],
    ["R07", "加氢扩展", "INT06 ⇄ MID（H*迁移）", "INT069748648；CI-NEB9796856；MID9737143", "Grade A；VFA9798421；正式能垒未登记", "兼容电子能垒登记；局部活性集与全反应热校正对齐", "和R06、R08分开，不把两次迁移压成一个峰"],
    ["R08", "加氢扩展", "MID [CH]–[C]–[O]* + H* ⇄ [CH]–[C]–OH*", "MID9737143；TS9746548；FS-A9725471", "局部O–H成键电子能垒已接受", "IS/MID/FS和TS一致活性集热校正、反应池引用", "只代表MID到FS的O–H成键段，不代表完整加氢路径"],
    ["R09", "竞争支路", "CH* + H* ⇄ CH₂*", "IS-A9701350；TS9709074；FS9622444", "电子能垒已接受", "热校正；与偶联反应共用CH/H/CO池的参考转换", "作为竞争分流；不能仅据本步报告CH₄选择性"],
    ["R10", "排氧扩展", "O* + H* ⇄ OH*", "O/OH/H已有吸附记录；匹配共吸附IS/FS待核", "未检出本步已接受能垒", "共吸附端点、TS及自由能；先查已有结构", "完整进料模型需要排氧通道，局部模型不冒称闭合"],
    ["R11", "排氧扩展", "OH* + H* ⇄ H₂O*", "OH/H/H₂O参考存在；反应端点待核", "未检出本步已接受能垒", "反应就位端点、TS或有依据的动力学处理、自由能", "不得用H₂O吸附能代替水生成能垒"],
    ["R12", "排氧扩展", "H₂O* ⇄ H₂O(g)", "已有H₂O吸附/气相参考；选用位点待核", "参考记录，不等于脱附动力学已具备", "气相化学势、脱附/再吸附模型、标准态", "若有无垒吸附依据可不另算TS；仍需可逆速率模型"],
    ["R13", "产物边界", "[CH]–[C]–OH* ⇄ 同连接气相C₂H₂O", "FS-A9725471；对应气相异构体待核", "不能把吸附态形成当成气相产物生成", "气相异构体/稳定性、脱附或后续转化、逆过程", "不得添加任意不可逆产物汇来制造稳态TOF"],
]

MAP = {"R03": "fe110_co_dissociation_topic1_9558184_to_9622455",
       "R04": "fe110_c_h_to_ch_A9715450_to_9573951",
       "R08": "fe110_c2ho_h_hydrogen_transfer_MID9737143_to_FSA9725471",
       "R09": "fe110_ch_h_to_ch2_A9701350_to_9622444"}


def main():
    if OUT.exists():
        raise ValueError("Inventory destination exists;inspect instead of overwriting")
    with open_registry(ROOT / "data/project_registry.sqlite3") as connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        barriers = [dict(row) for row in connection.execute("SELECT * FROM ts_barriers WHERE validation_status='accepted'")]
        validations = [dict(row) for row in connection.execute("SELECT * FROM ts_validations WHERE grade='A'")]
        result_ids = sorted({barrier[k] for barrier in barriers for k in ("initial_result_id", "ts_result_id", "final_result_id")})
        result_ids += list(load_json_object(BASE / "local_triplet_review_20261112_v1/reaction_contract.reviewed.json")["endpoints"][key]["static_result_id"] for key in ("initial", "final"))
        results = [dict(row) for row in connection.execute("SELECT * FROM results WHERE result_id IN (" + ",".join("?" for _ in result_ids) + ")", result_ids)]
        source_ids = sorted({row["source_file_id"] for row in results} | {row["frequency_output_file_id"] for row in validations})
        files = [dict(row) for row in connection.execute("SELECT * FROM files WHERE file_id IN (" + ",".join("?" for _ in source_ids) + ")", source_ids)]
        thermo = connection.execute("SELECT COUNT(*) FROM results WHERE lower(result_name) LIKE '%free_energy%' OR lower(result_name) LIKE '%gibbs%' OR lower(result_name) LIKE '%zpe%' OR lower(result_name) LIKE '%entropy%'").fetchone()[0]
        connection.rollback()
    by_reaction = {row["reaction_id"]: row for row in barriers}
    selected = [by_reaction[key] for key in MAP.values()]
    if len({row[0] for row in ROWS}) != len(ROWS) or len(selected) != 4:
        raise ValueError("Missing/duplicate inventory identities")
    for item in selected:
        if (not all(math.isfinite(item[k]) for k in ("forward_barrier_ev", "reverse_barrier_ev", "reaction_energy_ev"))
                or abs(item["forward_barrier_ev"] - item["reverse_barrier_ev"] - item["reaction_energy_ev"]) > 1e-10
                or item["energy_convention"] != "fe110_converged_toten_sigma0p20_v1"):
            raise ValueError("Registered electronic-energy consistency failed")
    row_data = []
    for row in ROWS:
        barrier = by_reaction.get(MAP.get(row[0]))
        row_data.append({"step_id": row[0], "scope": row[1], "chemical_change": row[2], "selected_structures": row[3],
            "evidence": row[4], "missing_parameters": row[5], "next_action": row[6],
            "forward_electronic_barrier_ev": barrier["forward_barrier_ev"] if barrier else None,
            "barrier_set_id": barrier["barrier_set_id"] if barrier else None,
            "status": "draft_for_network_review", "site_balance_status": "needs_site_footprint_review",
            "formal_kinetics_input": False})
    rsi_dir = Path("C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/runs/mkm_c1_c2_inventory_20261116_v1")
    rsi = load_json_object(rsi_dir / "run_receipt.json")
    payload = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "client_date": "2026-11-16 Asia/Shanghai",
        "status": "DRAFT_FOR_NETWORK_REVIEW_NOT_EXECUTABLE_MKM", "rows": row_data,
        "source_registry": str(ROOT / "data/project_registry.sqlite3"), "registry_read_only": True,
        "registered_barriers": barriers, "registered_grade_a_validations": validations,
        "registered_results": results, "registered_source_files": files, "thermo_result_name_matches": thermo,
        "thermo_search_limit": "Name-based registry search;not proof that no raw frequencies or unregistered corrections exist",
        "minimum_network": {"first_phase": "Reversible CH+CO reactive-pair conversion using9839757/9842136;local transient or conditional activity model,not overall steady TOF",
            "extensions_after_pool_alignment": ["CH hydrogenation competition", "explicit H migration and O-H formation"],
            "full_feed_requirements": ["CO/H2 supply", "O removal/water release", "physical product boundary"],
            "initial_coverages_temperature_pressures": None, "steady_state_product_sink_assumed": False,
            "three_C2HO_states_may_not_be_merged": ["FS9842136", "IS-A9725473", "MID9737143"]},
        "rsi": {key: rsi.get(key) for key in ("status", "problem", "model_turns_started", "host_tool_executions")},
        "scientific_execution": {"new_VASP": False, "new_GPU": False, "MKM_run": False, "registry_write": False}}
    OUT.mkdir(parents=True)
    write_json_exclusive(OUT / "inventory.json", payload)
    write_json_exclusive(OUT / "verification.json", {"status": "PASS", "review_rows": len(row_data),
        "accepted_electronic_barriers": len(selected), "grade_a_records": len(validations),
        "energy_identity_checks": 4, "registry_read_only": True,
        "site_balance_approved": False, "formal_MKM_ready": False, "inventory_sha256": sha256_file(OUT / "inventory.json")})
    print({"rows": len(row_data), "accepted_barriers": len(selected), "grade_a": len(validations), "formal_MKM_ready": False})


if __name__ == "__main__":
    main()
