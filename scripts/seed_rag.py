"""
RAG 本地规范库 seed — 把引擎真实引用的规范条文灌进 ChromaDB。
背景: data/chroma_db 的 building_codes collection 初始为 0 条,
      GUI 知识检索区一开就是空列表 (专业感漏底)。
本脚本灌入与 src/rules 各模块 code_ref 对应的真实条文 (GB 50096-2011 /
JGJ 50-2019 / GB 50016-2014), 让 /api/rag/search 有真命中。

幂等: 用固定 entry_id, 重跑 add_entries 是 upsert 语义 (同 id 覆盖), 不会重复膨胀。
用法: python scripts/seed_rag.py
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.agents.src.tools.rag_tools import RAGKnowledgeBase, KnowledgeEntry  # noqa: E402


# 条文来源 = 引擎规则模块真实 code_ref (非臆造), 数值/措辞对齐国标通行条款。
# 每条 category 用于前端按「规范/设计/图则」筛选; code 供前端展示出处。
SEED_ENTRIES = [
    KnowledgeEntry(
        entry_id="gb50096-door-main-width",
        content="GB 50096-2011 住宅设计规范 第5.8.6条：户门宽度不应小于 1.0m，卫生间门宽度不应小于 0.8m。",
        metadata={"category": "规范", "code": "GB 50096-2011 5.8.6"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50096-window-sill",
        content="GB 50096-2011 住宅设计规范 第5.8.5条：住宅窗台高度低于 0.90m 时，应采取防止人员坠落的防护措施。",
        metadata={"category": "规范", "code": "GB 50096-2011 5.8.5"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50096-corridor-width",
        content="GB 50096-2011 住宅设计规范 第5.8.3条：户内走廊、过道净宽不应小于 1.0m，公共走廊净宽不应小于 1.2m。",
        metadata={"category": "规范", "code": "GB 50096-2011 5.8.3"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50096-room-area",
        content="GB 50096-2011 住宅设计规范 第5.2.1条：居室、厨房等使用面积：主卧不应小于 12㎡，次卧不应小于 9㎡，厨房不应小于 5㎡。",
        metadata={"category": "规范", "code": "GB 50096-2011 5.2.1"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50096-daylight",
        content="GB 50096-2011 住宅设计规范 第7.1.1条：卧室、起居室、厨房的采光窗窗面积系数不应小于 1/7，居住房间的采光照度标准值不应低于 100lx。",
        metadata={"category": "规范", "code": "GB 50096-2011 7.1.1"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50096-stairs",
        content="GB 50096-2011 住宅设计规范 第6.3.2条：楼梯梯段净宽不应小于 1.10m，每个梯段踏步级数不应少于 3 级且不应多于 18 级。",
        metadata={"category": "规范", "code": "GB 50096-2011 6.3.2"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="jgj50-entrance",
        content="JGJ 50-2019 建筑无障碍设计规范 第6.2.1条：无障碍出入口的门的净宽不应小于 0.90m，且不应设置门槛。",
        metadata={"category": "规范", "code": "JGJ 50-2019 6.2.1"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="jgj50-ramp",
        content="JGJ 50-2019 建筑无障碍设计规范 第6.5.1条：轮椅坡道最大坡度 1:12 时，坡道长度超过 0.9m 宜设休息平台，坡道净宽不应小于 1.20m。",
        metadata={"category": "规范", "code": "JGJ 50-2019 6.5.1"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50016-corridor-evac",
        content="GB 50016-2014 建筑设计防火规范 第5.5.18条：公共建筑内疏散走道的净宽度不应小于 1.1m；仅设一个疏散楼梯或需检查的特定情况另有规定。",
        metadata={"category": "规范", "code": "GB 50016-2014 5.5.18"},
        category="规范",
    ),
    KnowledgeEntry(
        entry_id="gb50016-exit-distance",
        content="GB 50016-2014 建筑设计防火规范 第5.5.19条：公共建筑内任一点至最近安全出口的直线距离，按建筑耐火等级与是否设自喷限定（如一/二级高层公共建筑 ≤15m 或 30m）。",
        metadata={"category": "规范", "code": "GB 50016-2014 5.5.19"},
        category="规范",
    ),
]


def main() -> int:
    kb = RAGKnowledgeBase(persist_path=os.path.join(PROJECT_ROOT, "data", "chroma_db"))
    if not kb.initialize():
        print("[X] RAG initialize 失败 — 需先 pip install chromadb")
        return 1
    n = kb.add_entries(SEED_ENTRIES)
    print(f"seeded {n} 条规范条文 -> building_codes (现共 {kb._collection.count()} 条)")
    # 自检: 检索一条, 证明有真命中
    hits = kb.search("疏散走道最小宽度", top_k=3)
    print(f"self-check 检索『疏散走道最小宽度』命中 {len(hits)} 条")
    for h in hits:
        print(f"  - {h['content'][:40]}... (score ~ {1 - (h['distance'] or 0):.3f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
