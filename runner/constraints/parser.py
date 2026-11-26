"""結合位點約束解析：使用者語法（對象永遠 Chain A）→ 結構化 restraint。

支援：
  A:120-140            區段（range）
  A:Y45,A:K48,A:D52    指定殘基（residues）
  A:120-140;A:220-235  多結合區（; 或換行分隔）
  （空字串）           原生預測（free）

輸出給各引擎 adapter 使用（to_chai1 / to_boltz2，見 TODO）。
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


@dataclass
class Constraint:
    mode: str                       # residues | range | multi_region | free
    chain: str = "A"
    residues: list[int] = field(default_factory=list)  # 展平後的殘基序號
    regions: list[tuple[int, int]] = field(default_factory=list)
    max_dist: float = 8.0
    restraint_type: str = "contact"  # contact | pocket | docking


def _parse_token(tok: str) -> tuple[list[int], list[tuple[int, int]]]:
    """解析單一 token，如 'A:120-140' 或 'A:Y45'。回傳 (residues, regions)。"""
    tok = tok.strip()
    if not tok:
        return [], []
    body = tok.split(":", 1)[1] if ":" in tok else tok
    m = re.match(r"^[A-Za-z]?(\d+)\s*-\s*[A-Za-z]?(\d+)$", body)  # 區段 120-140 / Y120-Y140
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return [], [(min(a, b), max(a, b))]
    m = re.match(r"^[A-Za-z]?(\d+)$", body)                       # 單一殘基 Y45 / 45
    if m:
        return [int(m.group(1))], []
    raise ValueError(f"無法解析約束 token: {tok!r}")


def parse_constraint(spec: str, max_dist: float = 8.0) -> Constraint:
    spec = (spec or "").strip()
    if not spec:
        return Constraint(mode="free")
    tokens = [t for t in re.split(r"[;,\n]", spec) if t.strip()]
    residues: list[int] = []
    regions: list[tuple[int, int]] = []
    for t in tokens:
        r, g = _parse_token(t)
        residues += r
        regions += g
    if regions and (len(regions) + (1 if residues else 0)) > 1:
        mode = "multi_region"
    elif regions:
        mode = "range"
    else:
        mode = "residues"
    rtype = "pocket" if regions else "contact"
    return Constraint(mode=mode, residues=sorted(set(residues)), regions=regions,
                      max_dist=max_dist, restraint_type=rtype)


def constrained_residues(c: Constraint) -> list[int]:
    """展平所有被約束的 Chain A 殘基序號（供後處理 contact filter 用）。"""
    out = list(c.residues)
    for a, b in c.regions:
        out += list(range(a, b + 1))
    return sorted(set(out))


CHAI_HEADER = ("restraint_id,chainA,res_idxA,chainB,res_idxB,connection_type,"
               "confidence,min_distance_angstrom,max_distance_angstrom,comment")


def to_chai1(c: Constraint, protein_seq: str,
             protein_chain: str = "A", peptide_chain: str = "B") -> str | None:
    """約束 → Chai-1 restraints CSV 內容。回傳 None 表示無約束（原生預測）。

    語意：我們只指定 Chain A(protein) 的位點，peptide(Chain B) 任一殘基須靠近 →
    正好是 Chai 的 *pocket* restraint（res_idxA 留空=binder 任一殘基，
    res_idxB=protein 指定殘基）。每個被約束殘基產生一條 pocket restraint。

    Chai 會核對 res_idx 的「殘基字母+1-based 序號」與輸入序列相符，故需查序列。
    """
    if c.mode == "free":
        return None
    rows = [CHAI_HEADER]
    for i, resi in enumerate(constrained_residues(c)):
        if resi < 1 or resi > len(protein_seq):
            raise ValueError(f"約束殘基 {resi} 超出 protein 長度 {len(protein_seq)}")
        letter = protein_seq[resi - 1]
        # chainA 欄=binder(peptide, 任一殘基, res 留空)；chainB 欄=protein 指定殘基
        rows.append(
            f"r{i},{peptide_chain},,{protein_chain},{letter}{resi},pocket,"
            f"1.0,0.0,{c.max_dist},auto-site-{resi}"
        )
    return "\n".join(rows) + "\n"


def build_fasta(protein_seq: str, peptide_seq: str) -> str:
    """Chai-1 FASTA：第一條=Chain A(protein)，第二條=Chain B(peptide)。"""
    return (f">protein|name=chainA\n{protein_seq}\n"
            f">protein|name=chainB\n{peptide_seq}\n")


# TODO(Phase 3)：Boltz-2 adapter（YAML constraints：pocket/contact + steering）
# def to_boltz2(c: Constraint) -> dict: ...


if __name__ == "__main__":
    import sys
    c = parse_constraint(sys.argv[1] if len(sys.argv) > 1 else "A:120-140")
    print(c)
    print("constrained residues:", constrained_residues(c))
