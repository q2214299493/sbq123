"""Render verified coordinates and the requested structure/coordination review."""
from __future__ import annotations

from pathlib import Path
import zipfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.adsorption.build_fe110_care_batch import display_coordinates, draw_pose
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid, write_json_exclusive
from .prepare import GRAPHS, OUT, ROOT, SLAB


REPORT = ROOT / "docs/reviews/fe110_c2_site_supplement_20261106.md"
STAGES = {"cached_DFT_output": "既有DFT终点", "first_DFT_input_source_hash_verified": "既有DFT输入",
          "original_seed": "既有顶位种子（未优化）"}
SITES = {"top": "顶位", "short_bridge": "短桥", "long_bridge": "长桥", "hollow": "空位"}


def label_pose(axes, pose, slab, title):
    draw_pose(axes, pose, slab, title)
    cart = display_coordinates(pose)
    ads = cart[45:]
    axes[0].set_xlim(min(-3.5, ads[:, 0].min() - .8), max(3.5, ads[:, 0].max() + .8))
    axes[0].set_ylim(min(-3.5, ads[:, 1].min() - .8), max(3.5, ads[:, 1].max() + .8))
    axes[0].set_title(title + "\n俯视 / TOP", fontsize=10)
    axes[1].set_title(title + "\n侧视 / SIDE", fontsize=10)
    for fe in range(36, 45):
        x, y = cart[fe, :2]
        axes[0].annotate(f"Fe{fe}", (x, y), xytext=(-12, -14), textcoords="offset points",
                         fontsize=7, color="#616975")
    return cart


def drawings(manifest, slab):
    images = []
    for species, refs in manifest["reference_structures_not_new_jobs"].items():
        new = [c for c in manifest["candidates"] if c["species_number"] == species]
        columns = [(r["path"], f"REF {r['name']}\n{STAGES[r['stage']]}") for r in refs]
        columns += [(r["structure"], f"NEW {r['name']}\n" + ("恢复完整种子" if r["byte_exact_recovery"] else "新位点探索构造")) for r in new]
        fig, axes = plt.subplots(2, len(columns), figsize=(5.8 * len(columns), 9), constrained_layout=True, squeeze=False)
        for col, (path, title) in enumerate(columns):
            label_pose(axes[:, col], read_poscar(Path(path)), slab, title)
        fig.suptitle(f"{species} | {GRAPHS[species]} | Fe(110)\nNEW均未优化、未排序；REF仅作已有配位比较。Fe灰/C黑/O红/H蓝；编号零基。表面局部视图，完整Fe45见POSCAR。", fontsize=13)
        target = OUT / f"{species}_review.png"
        if target.exists():
            raise FileExistsError(target)
        fig.savefig(target, dpi=150)
        plt.close(fig)
        images.append(target)
    fig, axes = plt.subplots(4, 3, figsize=(16, 19), constrained_layout=True)
    for axis, item in zip(axes.flat, manifest["candidates"], strict=True):
        spare = plt.figure().add_subplot()
        pose = read_poscar(Path(item["structure"]))
        label_pose([axis, spare], pose, slab, item["name"])
        plt.close(spare.figure)
        axis.set_title(item["name"] + " | " + GRAPHS[item["species_number"]], fontsize=11)
        axis.set_xlabel("")
        axis.set_ylabel("")
    fig.suptitle("Fe(110) 12个补充候选：俯视总览\n全部为待审初始构型，非已优化稳定态。详细侧视、参考构型、配位表见审核报告。", fontsize=16)
    overview = OUT / "overview.png"
    if overview.exists():
        raise FileExistsError(overview)
    fig.savefig(overview, dpi=150)
    plt.close(fig)
    return images, overview


def closest_text(atom):
    return "; ".join(f"Fe{f['Fe_0based']}: {f['distance_A']:.3f}" for f in atom["nearest_Fe"])


def report(manifest, verification, images, overview):
    text = ["# Fe(110)补充位点：12个构型待审核", "",
        "日期：2026-11-06（Asia/Shanghai）。本轮仅本机构造/回读/绘图，GPU=0、VASP=0；未优化、未能量排序、未提交。",
        "", "## 结论与审核边界", "",
        "- 9个物种共补12个候选：05、06、18各2个；07、09、11、12、13、14各1个。",
        "- 7个为已审原始完整种子的原字节恢复，5个为本地几何模板的新位点构造。参考图中的REF不是新任务。",
        "- 06原始A/B同属双C接近同Fe的核心配位，故仅恢复A；另构造C46空位主锚定，不用B的姿态变化充数。12仅恢复原始A，B仍留作后备。",
        "- 每组图显示既有参考模式与新增模式，供审核三个非等价核心配位的覆盖；不是声称已获得三个稳定极小值。",
        "- 新18的C45分别为短桥/长桥；绕O47–C45键调整H48所在分支的二面角以减少低H接触，保留全部键长、键角和H归属。该扭转不是新增位点计数依据。",
        "- 资料策略为复用已验证本地结构；既有有限范围白名单无匹配记录只作背景，本次无新增外部结构或外部能量，也不冒称文献最稳前三。",
        "", "## 总览", "", f"![12个补充候选俯视图]({overview.as_posix()})", "",
        "距离单位Å；所有C/O/H/Fe编号均为零基。最近Fe与投影位置是几何信息，不自动等于成键数。抬起原子的hollow/top投影不算该原子吸附。",
        "", "|候选|连接方式|拟审核的不同配位|最近H–Fe|软提示|", "|---|---|---|---:|---|"]
    for item in manifest["candidates"]:
        warning = "H–Fe 1.870、最低高度1.556" if item["name"] == "06_S1" else "最低高度1.534" if item["name"] == "09_S1" else "无"
        text.append(f"|{item['name']}|`{item['target_graph']}`|{item['note_zh']}|{item['geometry']['nearest_h_fe_angstrom']:.3f}|{warning}|")
    verified = {r["name"]: r for r in verification["records"]}
    for species, image in zip(GRAPHS, images, strict=True):
        text.extend(["", f"## {species}：`{GRAPHS[species]}`", "", f"![{species}俯视与侧视]({image.as_posix()})", ""])
        for item in [c for c in manifest["candidates"] if c["species_number"] == species]:
            kind = "原字节恢复" if item["byte_exact_recovery"] else "探索构造（非DFT结果）"
            text.extend([f"### {item['name']} — {kind}", "", item["note_zh"], "",
                f"[POSCAR]({Path(item['structure']).as_posix()})；来源：{item['construction']['source_name']} / {item['source_role']}。",
                "", "|原子|相连H数|最近理想投影（横向偏差Å）|最近3个Fe及距离Å|", "|---|---:|---|---|"])
            for atom in item["saved_geometry"]["heavy_atoms"]:
                site = atom["nearest_xy_projection"]
                text.append(f"|{atom['element']}{atom['atom_0based']}|{atom['bonded_H_count']}|{SITES[site]}（{atom['xy_projection_distances_A'][site]:.3f}）|{closest_text(atom)}|")
            bonds = item["geometry"]["bond_distances"]
            bond_text = "; ".join(f"{b['pair']}({b['atoms_0based'][0]}–{b['atoms_0based'][1]})={b['distance_A']:.3f}" for b in bonds)
            check = verified[item["name"]]
            text.extend(["", "内部键长：" + bond_text + "。", "",
                f"独立回读：最小接触（排除吸附物共价键）{check['minimum_contact_excluding_adsorbate_bonds_A']:.3f} Å；最低吸附原子高度{check['minimum_height_above_Fe_A']:.3f} Å。",
                "原始种子保持原字节。" if item["byte_exact_recovery"] else "重定位/扭转仅改变吸附几何；全部原共价键长和内部键角保持。", ""])
            if item["geometry"]["warnings"]:
                text.extend(["软提示：该候选触及已有初始结构的早期复核提示，不等于失败或稳定。保留原坐标交用户判断，不因此放宽阻断标准或自动提交。", ""])
    minimum = min(p["seed_only_RMSD_without_height_padding_A"] for p in manifest["seed_only_comparisons"])
    max_bond = max(r["maximum_internal_bond_delta_A"] for r in verification["records"])
    max_angle = max(r["maximum_internal_angle_delta_deg"] for r in verification["records"])
    text.extend(["## 验证结果、限制与下一步", "",
        f"- 12份保存文件均通过独立枚举xy周期镜像的组成、原子顺序、原子级连接/H归属、晶胞、Fe45坐标、底部18Fe固定及吸附物全可动检查。内部键长最大变化{max_bond:.3g} Å，键角最大变化{max_angle:.3g}°。",
        f"- 与每组参考及新增候选共27组初始几何比较，去除统一高度填充后最小RMSD为{minimum:.3f} Å。它是防止近重复种子，不证明不同稳定态；核心配位是否合理仍需用户审阅。",
        "- 06_S1、09_S1的软提示见表；其余10份无这两项提示。全部通过既有初始碰撞/高度/完整连接检查，未引入新的放宽参数。",
        "- 只提供POSCAR、几何证据和图，不生成INCAR/KPOINTS/POTCAR/作业脚本。未运行模型、GPU、VASP、能量/力优化、训练或数据库/Excel写入。",
        "- 新候选仍可能迁移、脱H或解离；本次不能确定稳定性、能量排序或实际加速收益。",
        "- 科研助手入口本轮调用一次，因既有Codex程序路径失效而止于准入；无研究轮次、无新增接受经验。依据为实际本地结构。[科研助手看板](C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/policy_store/dashboard/index.html)。",
        "- 下一步只需用户逐项选择保留/修改/剔除；审核前不进入GPU或VASP。", "",
        f"[构型与源哈希清单]({(OUT / 'candidate_review.json').as_posix()}) · [独立回读检查]({(OUT / 'independent_verification.json').as_posix()})", ""])
    with REPORT.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(text))


def main():
    manifest = load_json_object(OUT / "candidate_review.json")
    check = load_json_object(OUT / "independent_verification.json")
    assert source_file_manifest_valid(manifest) and check["status"] == "PASS_GEOMETRY_READBACK_ONLY"
    assert sha256_file(OUT / "candidate_review.json") == check["manifest_sha256"]
    if REPORT.exists():
        raise FileExistsError(REPORT)
    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams["font.family"] = "Microsoft YaHei"
    plt.rcParams["axes.unicode_minus"] = False
    images, overview = drawings(manifest, read_poscar(SLAB))
    report(manifest, check, images, overview)
    bundle = OUT.parent / "Fe110_C2_supplement_review.zip"
    with zipfile.ZipFile(bundle, "x", zipfile.ZIP_DEFLATED) as handle:
        for item in manifest["candidates"]:
            path = Path(item["structure"])
            handle.write(path, f"{item['name']}/POSCAR")
        for path in [*images, overview, REPORT, OUT / "candidate_review.json", OUT / "independent_verification.json"]:
            handle.write(path, path.name)
    write_json_exclusive(OUT / "delivery_receipt.json", {"bundle": str(bundle), "bundle_sha256": sha256_file(bundle),
        "report": str(REPORT), "report_sha256": sha256_file(REPORT), "renderer_sha256": sha256_file(Path(__file__)),
        "images": [{"path": str(path), "sha256": sha256_file(path)} for path in [*images, overview]],
        "scientific_acceptance": False, "execution": {"GPU": 0, "VASP": 0}})
    print("REVIEW_DELIVERED", len(manifest["candidates"]), "POSCARs;9 comparison figures;1 overview;no calculations")


if __name__ == "__main__":
    main()
