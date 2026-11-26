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
    return (f"ATOM  {serial:>5} {name:<4}{resn:>3} {chain}{resi:>4}    "
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


def run_real_engine(spec, con, out_dir):
    """TODO(Phase 1)：接真實引擎。
    chai-1 範例流程：
      1. parser.to_chai1(con) → restraints.csv
      2. chai-lab fold：protein(Chain A) + peptide(Chain B) + restraints
         低記憶體設定：關 templates、縮 MSA、開 chunking（配合 12GB）
      3. 讀輸出 cif → 轉 pdb；讀 pLDDT/PAE/ipTM
      4. 後處理：量 Chain A 約束殘基與 Chain B 最小距離 → contact_satisfied
    """
    raise NotImplementedError("real engine not wired yet; use engine=stub")


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
