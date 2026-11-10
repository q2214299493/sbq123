"""Review final geometry/force correspondence and diagnose the 18_S1 event."""
from pathlib import Path
import json

import matplotlib.pyplot as plt
import numpy as np
from ase.io import read

from scripts.adsorption.build_fe110_adsorption import expanded_symbols, fe110_anchor_site_distances, read_poscar
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.workflow_geometry import minimum_image_delta_xy
from .collect import OUT, ROOT


def force_correspondence(folder, pose):
    with (folder/"OUTCAR").open("rb") as source:
        source.seek(max(0,(folder/"OUTCAR").stat().st_size-2*1024*1024))
        text=source.read().decode("utf8",errors="replace")
    offset=text.rfind("TOTAL-FORCE (eV/Angst)")
    if offset<0:
        raise ValueError("Final complete force block not in bounded tail: "+str(folder))
    rows=[]
    for line in text[offset:].splitlines()[2:]:
        parts=line.split()
        if len(parts)!=6:
            if rows:break
            continue
        try:rows.append([float(x) for x in parts])
        except ValueError:break
    if len(rows)!=len(pose.frac):
        raise ValueError("Incomplete final force/position block.")
    raw=np.asarray(rows)
    delta=minimum_image_delta_xy(raw[:,:3]@np.linalg.inv(pose.cell)-pose.frac)@pose.cell
    error=float(np.linalg.norm(delta,axis=1).max())
    return {"position_max_error_A":error,"coordinate_force_correspondence_passed":error<2e-5,
            "raw_fmax_movable_eV_A":float(np.linalg.norm(raw[18:,3:],axis=1).max())}


def render(names, target):
    plt.switch_backend("Agg")
    fig,axes=plt.subplots(2,len(names),figsize=(3.5*len(names),6.5),squeeze=False)
    colors={"C":"#202c39","O":"#dc2626","H":"#38bdf8"}
    for col,name in enumerate(names):
        pose=read_poscar(OUT/"sources"/name/"CONTCAR")
        symbols=expanded_symbols(pose)
        frac=pose.frac.copy()
        frac[45:]=frac[45]+minimum_image_delta_xy(frac[45:]-frac[45])
        cart=frac@pose.cell
        center=cart[45:].mean(axis=0)
        surface=np.argsort(cart[:45,2])[-18:]
        for tx in (-1,0,1):
            for ty in (-1,0,1):
                q=cart+np.array([tx,ty,0])@pose.cell
                for row,dims in enumerate(((0,1),(0,2))):
                    axes[row,col].scatter(q[surface,dims[0]],q[surface,dims[1]],s=75,c="#a1a1aa",alpha=.4)
        for row,dims in enumerate(((0,1),(0,2))):
            ax=axes[row,col]
            for atom in range(45,len(cart)):
                ax.scatter(cart[atom,dims[0]],cart[atom,dims[1]],s=85 if symbols[atom]!="H" else 45,
                           c=colors[symbols[atom]],edgecolors="white",zorder=3)
                ax.annotate(symbols[atom]+str(atom),(cart[atom,dims[0]],cart[atom,dims[1]]),fontsize=7,xytext=(3,3),textcoords="offset points")
            ax.set_xlim(center[0]-4,center[0]+4)
            ax.set_ylim((center[1]-4,center[1]+4) if row==0 else (cart[:45,2].max()-2,cart[45:,2].max()+1))
            ax.set_aspect("equal")
            ax.grid(alpha=.12)
        axes[0,col].set_title(name,fontsize=11)
    fig.suptitle("Fe(110) final VASP structures; grey Fe / black C / red O / blue H; labels are zero-based",fontsize=11)
    fig.tight_layout(rect=(0,0,1,.94))
    fig.savefig(target,dpi=140)
    plt.close(fig)


def main():
    target=OUT/"force_geometry_final_review.json"
    if target.exists():
        raise SystemExit("Preserve the existing final review.")
    analysis=load_json_object(OUT/"completion_geometry_review.json")
    slab=read_poscar(ROOT/"calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR")
    records=[]
    for row in analysis["records"]:
        folder=Path(row["directory"])
        pose=read_poscar(folder/"CONTCAR")
        initial=read_poscar(folder/"POSCAR")
        geometric=force_correspondence(folder,pose)
        geometric["maximum_Fe_displacement_A"]=float(np.linalg.norm(minimum_image_delta_xy(pose.frac[:45]-initial.frac[:45])@pose.cell,axis=1).max())
        geometric["projection_distances"]={str(i):fe110_anchor_site_distances(slab,pose.frac[i]) for i in row["adsorbate_indices"] if row["symbols"][i]!="H"}
        records.append({"name":row["name"],**geometric})
    folder=OUT/"sources/18_S1"
    frames=read(folder/"XDATCAR",index=":",format="vasp-xdatcar")
    history=[]
    for i,frame in enumerate(frames,1):
        frame.pbc=[True,True,False]
        history.append({"frame":i,"C45_H48_A":float(frame.get_distance(45,48,mic=True)),
                        "nearest_H48_Fe_A":min(float(frame.get_distance(48,f,mic=True)) for f in range(45))})
    first=next((r for r in history if r["C45_H48_A"]>1.34),None)
    diagnosis={"name":"18_S1","event":"C45-H48 dehydrogenation to surface H; [C]-O-CH3 + H*, not gas desorption",
        "first_C_H_above_1p34_A_frame_diagnostic_only":first,"frames":len(frames),"history":history,
        "formal_product_minimum_accepted":False,"new_job_or_retry_authorized":False,
        "source_files":source_file_manifest([folder/x for x in ("POSCAR","CONTCAR","XDATCAR","OUTCAR","OSZICAR")])}
    write_json_exclusive(OUT/"18_S1_diagnosis.json",diagnosis)
    write_json_exclusive(target,{"status":"NUMERIC_GEOMETRY_PENDING_VISUAL_REVIEW","records":records,
        "source_files":source_file_manifest([OUT/"completion_geometry_review.json",Path(__file__)])})
    render(["05_S2","07_S1","12_S1","13_S1","18_S2"],OUT/"unique_final_structures.png")
    render(["06_S2","18_S1"],OUT/"ineligible_final_structures.png")
    print(json.dumps({"force_geometry":records,"18_S1_first_event":first},ensure_ascii=False))


if __name__=="__main__":
    main()
