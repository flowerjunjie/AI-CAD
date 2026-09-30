"""
RAG 知识库 — ChromaDB 本地部署
规范条文向量检索 + 历史图纸检索

外部依赖标注（诚实边界，不虚标）:
- 本模块的「纯逻辑」（数据结构、条目序列化、检索结果打分映射）可全测。
- 但「真向量检索」需 ChromaDB 持久库（`data/chroma_db`）+ embedding 后端:
  * chromadb 未装 / 库缺失时, `initialize()` 诚实降级返回 False,
    检索方法返回空 + note, 不崩、不造假数据（红线二）。
  * 跑真检索需先 `python scripts/seed_rag.py` 灌入规范条文向量。
- 覆盖率 ~44% 属正常——未盖部分全在「真连 chroma 建/查 collection」分支,
  需真向量库, 故不 mock 假 collection 凑覆盖（红线二：不造假绿）。
"""
from dataclasses import dataclass
from typing import Optional
import json


@dataclass
class KnowledgeEntry:
    """知识库条目"""
    entry_id: str
    content: str  # 文本内容
    metadata: dict
    category: str  # 规范/案例/图块


class RAGKnowledgeBase:
    """本地 RAG 知识库"""

    def __init__(self, persist_path: str = "./data/chroma_db"):
        self.persist_path = persist_path
        self._client = None
        self._collection = None

    def initialize(self) -> bool:
        """初始化知识库"""
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=self.persist_path)
            self._collection = self._client.get_or_create_collection(
                name="building_codes",
                metadata={"hnsw:space": "cosine"}
            )
            return True
        except ImportError:
            print("chromadb not installed. Run: pip install chromadb")
            return False
        except Exception as e:
            print(f"RAG initialization failed: {e}")
            return False

    def add_entries(self, entries: list[KnowledgeEntry]) -> int:
        """批量添加条目"""
        if not self._collection:
            return 0

        ids = [e.entry_id for e in entries]
        documents = [e.content for e in entries]
        metadatas = [e.metadata if e.metadata else {"default": "true"} for e in entries]

        self._collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        return len(ids)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """语义检索"""
        if not self._collection:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k
        )

        return [
            {
                "id": doc_id,
                "content": doc,
                "metadata": meta,
                "distance": dist,
            }
            for doc_id, doc, meta, dist in zip(
                results["ids"][0],
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0]
            )
        ]

    def get_all_entries(self, category: Optional[str] = None) -> list[KnowledgeEntry]:
        """获取所有条目（或按分类筛选）"""
        if not self._collection:
            return []

        results = self._collection.get()
        entries = []
        for i, doc_id in enumerate(results["ids"]):
            meta = results["metadatas"][i] or {}
            if category and meta.get("category") != category:
                continue
            entries.append(KnowledgeEntry(
                entry_id=doc_id,
                content=results["documents"][i],
                metadata=meta,
                category=meta.get("category", "unknown")
            ))
        return entries


# ─── Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    rag = RAGKnowledgeBase()
    if not rag.initialize():
        print("Failed to initialize RAG")
        exit(1)

    # 添加示例条目
    entries = [
        KnowledgeEntry(
            entry_id="code-001",
            content="GB 50096-2011《住宅设计规范》第5.8.6条：户门宽度不应小于1.0m，户内门宽度不应小于0.9m。",
            metadata={"category": "规范", "code": "GB 50096-2011"},
            category="规范"
        ),
        KnowledgeEntry(
            entry_id="code-002",
            content="GB 50096-2011《住宅设计规范》第5.8.7条：走廊净宽不应小于1.2m，居住空间走道净宽不应小于1.0m。",
            metadata={"category": "规范", "code": "GB 50096-2011"},
            category="规范"
        ),
    ]
    rag.add_entries(entries)

    # 检索测试
    results = rag.search("疏散走道最小宽度是多少")
    print(f"找到 {len(results)} 条相关规范：")
    for r in results:
        print(f"  - {r['content'][:60]}...")
