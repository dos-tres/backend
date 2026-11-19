"""청년정책 API(getPlcy) 실제 형식 + 카테고리 체계 확인.

  python tools/data_check/inspect_policies.py           # 전국 전체
  python tools/data_check/inspect_policies.py 11000     # 지역(zipCd) 제한

출력(data/runtime/data_check/policy/):
  sample_response.json   첫 페이지 원본 응답 (래퍼 구조 확인)
  raw.jsonl              전체 원본
  fields.csv             필드별 채움률/고유값/예시
  category_tree.csv      대분류(lclsfNm) x 중분류(mclsfNm) 건수 + 예시 정책명
  keywords.csv           정책키워드(plcyKywdNm) 빈도
  special_targets.csv    특화요건(sBizCd)·소득조건(earnCndSeCd) 분포
"""
import csv
import json
import sys
from collections import Counter, defaultdict

from common import OUT, dump_jsonl, fetch_all, field_profile, require_key

D = OUT / "policy"
SBIZ = {"0014001": "중소기업", "0014002": "여성", "0014003": "기초생활수급자", "0014004": "한부모가정",
        "0014005": "장애인", "0014006": "농업인", "0014007": "군인", "0014008": "지역인재",
        "0014009": "기타", "0014010": "제한없음"}
EARN = {"0043001": "무관", "0043002": "연소득", "0043003": "기타"}


def split(v):
    return [c.strip() for c in str(v or "").split(",") if c.strip()]


def write_csv(path, rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else [])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    key = require_key("YOUTH_POLICY_API_KEY")
    extra = {"zipCd": sys.argv[1]} if len(sys.argv) > 1 else None
    items, first = fetch_all("getPlcy", key, extra=extra)
    D.mkdir(parents=True, exist_ok=True)
    # 첫 응답은 목록을 2건으로 잘라 구조만 남김
    (D / "sample_response.json").write_text(json.dumps(first, ensure_ascii=False, indent=2)[:20000], encoding="utf-8")
    dump_jsonl(D / "raw.jsonl", items)
    write_csv(D / "fields.csv", field_profile(items))

    # 대분류 x 중분류. 한 정책에 여러 분류가 쉼표로 올 수 있어 쌍으로 펼친다.
    tree, examples = Counter(), defaultdict(list)
    for it in items:
        ls, ms = split(it.get("lclsfNm")), split(it.get("mclsfNm"))
        pairs = list(zip(ls, ms)) if len(ls) == len(ms) and ls else [(l, m) for l in ls or ["(없음)"] for m in ms or ["(없음)"]]
        for p in pairs:
            tree[p] += 1
            if len(examples[p]) < 5:
                examples[p].append(it.get("plcyNm", ""))
    write_csv(D / "category_tree.csv",
              [{"lclsfNm": l, "mclsfNm": m, "count": c, "examples": " / ".join(examples[(l, m)])}
               for (l, m), c in sorted(tree.items(), key=lambda x: (x[0][0], -x[1]))])

    kw = Counter(k for it in items for k in split(it.get("plcyKywdNm")))
    write_csv(D / "keywords.csv", [{"keyword": k, "count": c} for k, c in kw.most_common()])

    st = Counter()
    for it in items:
        for c in split(it.get("sbizCd") or it.get("sBizCd")):   # 실제 응답 필드명은 sbizCd
            st[("sbizCd", SBIZ.get(c, c))] += 1
        e = str(it.get("earnCndSeCd", "")).strip()
        st[("earnCndSeCd", EARN.get(e, e or "(없음)"))] += 1
    write_csv(D / "special_targets.csv", [{"field": f, "value": v, "count": c} for (f, v), c in st.most_common()])

    print(f"\n정책 {len(items)}건 → {D}")
    print("\n[대분류 > 중분류]")
    cur = None
    for (l, m), c in sorted(tree.items(), key=lambda x: (x[0][0], -x[1])):
        if l != cur:
            print(f"- {l}")
            cur = l
        print(f"    {m:20} {c:5}")
    print("\n[키워드 상위 30]", ", ".join(f"{k}({c})" for k, c in kw.most_common(30)))


if __name__ == "__main__":
    main()
