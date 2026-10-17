import argparse
import datetime
import os
import sys

# 상위 디렉토리(src)를 모듈 검색 경로에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from langchain_text_splitters import RecursiveCharacterTextSplitter

from chroma_client import get_chroma_client
from config import settings
from embedding_function import get_embedding_function

# 1. 시놀로지 NAS ChromaDB 연결
try:
    chroma_client = get_chroma_client()
    print(f"✅ ChromaDB 연결 성공: {settings.CHROMA_HOST}:{settings.CHROMA_PORT}")
except Exception as e:
    print(f"❌ ChromaDB 연결 실패: {e}")
    exit(1)

# 2. 임베딩 (Bifrost 경유)
print("⏳ 임베딩(bge-m3) 연결 중 — Bifrost 경유...")
ollama_ef = get_embedding_function()

# 3. 빈 컬렉션 연결 (사전에 수동으로 빈 상태여야 함)
collection = chroma_client.get_or_create_collection(
    name="my_wiki_db",
    embedding_function=ollama_ef
)

# 4. 대상 폴더 목록
target_dirs = [
    ("tech", settings.TECH_DIR),
    ("career", settings.CAREER_DIR),
    ("personal", settings.PERSONAL_DIR)
]

text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

parser = argparse.ArgumentParser(
    description="Vault 전체를 ChromaDB 로 재색인한다. 기본은 비파괴(upsert)."
)
parser.add_argument(
    "--prune",
    action="store_true",
    help=(
        "Vault 에 대응 파일이 없는 색인 문서(고아 레코드)를 삭제한다. "
        "기본은 꺼져 있다 — 켜면 데이터가 지워진다."
    ),
)
args = parser.parse_args()

total_files = 0
total_chunks = 0
seen_sources = set()

for category, dir_path in target_dirs:
    if not os.path.exists(dir_path):
        continue

    md_files = [f for f in os.listdir(dir_path) if f.endswith('.md')]
    if not md_files:
        continue

    print(f"\n📂 [{category.upper()}] 폴더 처리 중... ({len(md_files)}개 파일)")

    for file_name in md_files:
        file_path = os.path.join(dir_path, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            chunks = text_splitter.split_text(content)
            base_name = file_name.replace(".md", "")

            docs = []
            ids = []
            metadatas = []

            # modified_at 은 반드시 파일 mtime 이어야 한다 — now() 로 넣으면 전 문서가
            # 같은 값이 되어 "최신순" 정렬이 다시 무의미해진다(① 1-1 확정 사양).
            modified_at = datetime.datetime.fromtimestamp(
                os.path.getmtime(file_path)
            ).isoformat(timespec="seconds")

            for i, chunk in enumerate(chunks):
                docs.append(chunk)
                ids.append(f"{base_name}_chunk_{i}")
                metadatas.append({
                    "category": category,
                    "source": base_name,
                    "modified_at": modified_at,
                    "chunk_index": i,
                })

            if docs:
                # 분할 결과가 달라지면 예전 청크 id 가 남아 중복 결과를 낸다.
                try:
                    stale = collection.get(where={"source": base_name})
                    keep = set(ids)
                    stale_ids = [x for x in (stale.get("ids") or []) if x not in keep]
                    if stale_ids:
                        collection.delete(ids=stale_ids)
                        print(f"   · 구버전 청크 {len(stale_ids)}개 정리")
                except Exception as exc:
                    print(f"   · 구버전 청크 확인 실패(무시): {exc}")

                collection.upsert(documents=docs, ids=ids, metadatas=metadatas)
                seen_sources.add(base_name)
                total_files += 1
                total_chunks += len(docs)
                print(f"   ✓ {file_name} -> {len(docs)}개 청크 임베딩 완료")
        except Exception as e:
            print(f"   ❌ [오류] {file_name} 처리 실패 (건너뜀): {e}")

print(f"\n🎉 전체 재임베딩 완료! (총 {total_files}개 파일, {total_chunks}개 벡터 조각)")

# Vault 에 없는 색인 문서(고아 레코드) 점검. 원본이 지워졌는데 색인만 남은 것들이며,
# personal 분류가 섞여 있을 수 있어 조용히 두면 프라이버시 경계에 구멍이 된다.
everything = collection.get()
indexed_sources = {}
for meta in (everything.get("metadatas") or []):
    src = (meta or {}).get("source")
    if src:
        indexed_sources.setdefault(src, (meta or {}).get("category", "Unknown"))

orphans = {
    src: cat for src, cat in indexed_sources.items() if src not in seen_sources
}
print()
if not orphans:
    print("✅ 고아 레코드 없음 — 색인과 vault 가 일치합니다.")
else:
    print(f"⚠️ 고아 레코드 {len(orphans)}개 (vault 에 대응 파일 없음):")
    for src, cat in sorted(orphans.items()):
        flag = "   ← personal!" if cat != "tech" else ""
        print(f"   [{cat}] {src}{flag}")
    print()
    if not args.prune:
        print("   삭제하지 않았습니다. 지우려면 --prune 을 붙여 다시 실행하십시오.")
    else:
        removed = 0
        for src in orphans:
            got = collection.get(where={"source": src})
            ids_to_del = got.get("ids") or []
            if ids_to_del:
                collection.delete(ids=ids_to_del)
                removed += len(ids_to_del)
        print(f"🧹 --prune: 고아 청크 {removed}개 삭제 완료.")
