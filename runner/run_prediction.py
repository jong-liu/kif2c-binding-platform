#!/usr/bin/env python3
"""KIF2C 平台預測入口（runner 端）。

MVP 第一版：engine="stub" 產生「佔位結構 + 分數」，用來打通
「送單 → Actions → runner → 回寫結果 → 前端顯示/下載」整條管線，
不需等 Chai-1 權重。真實引擎在 run_real_engine() 裡接（見 TODO）。

用法：
    python runner/run_prediction.py --spec jobs/<id>.json --out results/<id>
產出：
    <out>/complex.pdb   結構（Chain A=protein, Chain B=peptide）
    <out>/scores.json   iptm / plddt / contact_satisfied / rank_score
    <out>/spec.json     原始 job spec（存證）
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from constraints.parser import parse_constraint, constrained_residues  # noqa: E402


def _seeded(seq: str, lo: float, hi: float) -> float:
    """由序列雜湊產生可重現的假分數（stub 用）。"""
    h = int(hashlib.sha256(seq.encode()).hexdigest(), 16)
    return round(lo + (h % 1000) / 1000 * (hi - lo), 3)


def _pdb_atom(serial, name, resn, chain, resi, x, y, z, elem):
    # 標準 PDB 固定欄位：name 13-16, altLoc 17, resName 18-20, chain 22, resSeq 23-26, x 31-38
    return (f"ATOM  {serial:>5} {name:<4} {resn:>3} {chain}{resi:>4}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00  0.00          {elem:>2}\n")


def make_stub_structure(protein_seq: str, peptide_seq: str, con) -> str:
    """產生最小 PDB：Chain A 沿 x 軸排 CA；Chain B 擺在被約束殘基附近。"""
    lines, serial = [], 1
    # Chain A：protein 主鏈 CA 佔位（每殘基 3.8 Å）
    for i, aa in enumerate(protein_seq or "G" * 20, start=1):
        x = i * 3.8
        lines.append(_pdb_atom(serial, "CA", "GLY", "A", i, x, 0.0, 0.0, "C"))
        serial += 1
    # 決定 peptide 擺放中心：被約束殘基的平均位置（free 則擺中段）
    res = constrained_residues(con)
    center_i = (sum(res) / len(res)) if res else max(1, len(protein_seq or "x") // 2)
    cx = center_i * 3.8
    # Chain B：peptide CA 沿 y 軸排在 protein 上方 ~6 Å（模擬結合在該位點）
    for j, aa in enumerate(peptide_seq or "A" * 8, start=1):
        lines.append(_pdb_atom(serial, "CA", "ALA", "B", j, cx + j * 1.0, 6.0 + j * 3.0, 0.0, "C"))
        serial += 1
    lines.append("END\n")
    return "".join(lines)


def _contact_satisfied(structure_path: str, con, cutoff: float) -> float | None:
    """後處理：量 Chain A 被約束殘基與 Chain B 的最小原子距離，回傳滿足比例。"""
    if con.mode == "free":
        return None
    import gemmi
    st = gemmi.read_structure(structure_path)
    model = st[0]
    b_atoms = [a.pos for ch in model if ch.name == "B" for res in ch for a in res]
    if not b_atoms:
        return None
    targets = set(constrained_residues(con))
    ok = 0
    total = 0
    for ch in model:
        if ch.name != "A":
            continue
        for res in ch:
            if res.seqid.num in targets:
                total += 1
                dmin = min((a.pos.dist(bp) for a in res for bp in b_atoms), default=1e9)
                if dmin <= cutoff:
                    ok += 1
    return round(ok / total, 3) if total else None


def run_real_engine(spec, con, out_dir):
    """Chai-1 真實預測。
    流程：build FASTA/restraints → run_inference → 挑最佳模型 →
    讀 ptm/iptm/plddt → 算 contact_satisfied → 輸出 complex.cif/pdb + scores.json。
    """
    import shutil
    import tempfile
    from pathlib import Path
    import numpy as np
    import gemmi
    from chai_lab.chai1 import run_inference
    from constraints.parser import to_chai1, build_fasta

    protein = spec["protein"]["sequence"]
    peptide = spec["peptide"]["sequence"]
    seed = int(spec.get("seed", 42))
    use_esm = bool(spec.get("use_esm", True))  # 12GB OOM 時可在 spec 設 false

    work = tempfile.mkdtemp(prefix="chai_")
    fasta_path = os.path.join(work, "input.fasta")
    with open(fasta_path, "w") as f:
        f.write(build_fasta(protein, peptide))

    restraints_csv = to_chai1(con, protein)
    constraint_path = None
    if restraints_csv:
        constraint_path = os.path.join(work, "restraints.csv")
        with open(constraint_path, "w") as f:
            f.write(restraints_csv)
        shutil.copy(constraint_path, os.path.join(out_dir, "restraints.csv"))

    chai_out = os.path.join(work, "outputs")  # run_inference 要求空目錄
    candidates = run_inference(
        fasta_file=Path(fasta_path),
        output_dir=Path(chai_out),
        constraint_path=(Path(constraint_path) if constraint_path else None),
        num_trunk_recycles=int(spec.get("num_trunk_recycles", 3)),
        num_diffn_timesteps=int(spec.get("num_diffn_timesteps", 200)),
        seed=seed,
        device="cuda:0",
        use_esm_embeddings=use_esm,
    )

    # 挑 aggregate_score 最高的模型
    agg = [rd.aggregate_score.item() for rd in candidates.ranking_data]
    best = int(np.argmax(agg))
    best_cif = str(candidates.cif_paths[best])

    # 讀分數 npz（鍵名防呆）
    npz = np.load(os.path.join(chai_out, f"scores.model_idx_{best}.npz"))
    def g(*names):
        for n in names:
            if n in npz.files:
                return float(np.mean(npz[n]))
        return None
    ptm = g("ptm", "aggregate_ptm")
    iptm = g("iptm", "aggregate_iptm")

    # 輸出結構：cif 原樣 + 轉 pdb 給前端
    shutil.copy(best_cif, os.path.join(out_dir, "complex.cif"))
    st = gemmi.read_structure(best_cif)
    st.setup_entities()
    with open(os.path.join(out_dir, "complex.pdb"), "w") as f:
        f.write(st.make_pdb_string())

    # pLDDT：Chai 把每原子信心寫在 B-factor 欄（0–100），取平均
    bvals = [a.b_iso for ch in st[0] for res in ch for a in res]
    plddt = round(sum(bvals) / len(bvals), 2) if bvals else None

    sat = _contact_satisfied(best_cif, con, con.max_dist)
    scores = {
        "engine": "chai-1",
        "engine_ver": "0.6.1",
        "plddt": plddt,
        "ptm": round(ptm, 3) if ptm is not None else None,
        "iptm": round(iptm, 3) if iptm is not None else None,
        "aggregate_score": round(agg[best], 3),
        "contact_satisfied": sat,
        "constraint_mode": con.mode,
        "constrained_residues": constrained_residues(con),
        "best_model_idx": best,
        "use_esm_embeddings": use_esm,
    }
    scores["rank_score"] = round((iptm or agg[best]) * (sat if sat is not None else 1.0), 3)

    with open(os.path.join(out_dir, "scores.json"), "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    shutil.rmtree(work, ignore_errors=True)
    print(f"✅ {spec.get('id')} (chai-1) 完成 → {out_dir} "
          f"(iptm={iptm}, plddt={plddt}, 約束滿足={sat})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)
    os.makedirs(args.out, exist_ok=True)

    protein = spec.get("protein", {}).get("sequence", "")
    peptide = spec.get("peptide", {}).get("sequence", "")
    con = parse_constraint(spec.get("constraint", ""))
    engine = spec.get("engine", "stub")

    if engine == "stub":
        pdb = make_stub_structure(protein, peptide, con)
        scores = {
            "engine": "stub",
            "plddt": _seeded(protein + peptide, 55, 90),
            "iptm": _seeded(peptide + protein, 0.3, 0.85),
            "contact_satisfied": 1.0 if con.mode != "free" else None,
            "constraint_mode": con.mode,
            "constrained_residues": constrained_residues(con),
            "note": "STUB 假結構，僅供管線測試；非真實預測。",
        }
        scores["rank_score"] = round(
            scores["iptm"] * (scores["contact_satisfied"] or 1.0), 3
        )
    else:
        run_real_engine(spec, con, args.out)  # 之後在這裡接 chai-1 / boltz-2
        return

    with open(os.path.join(args.out, "complex.pdb"), "w") as f:
        f.write(pdb)
    with open(os.path.join(args.out, "scores.json"), "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "spec.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    print(f"✅ {spec.get('id')} 完成 → {args.out} (iptm={scores['iptm']})")


if __name__ == "__main__":
    main()
