from __future__ import annotations

from collections import defaultdict
from typing import Any


# These are conceptual bridges, not chapter adjacency.  Each edge states the
# shared mechanism so the UI can teach why two points belong together.
CURATED_RELATIONS: tuple[tuple[str, str, str, str], ...] = (
    (
        "kp_co_co_memory_03", "kp_os_os_memory_05", "有限容量下的局部性与替换",
        "Cache 行和物理页框都是有限槽位；FIFO/LRU 等策略都在利用访问局部性决定淘汰对象。",
    ),
    (
        "kp_cn_cn_transport_04", "kp_os_os_process_04", "反馈控制与公平调度",
        "拥塞窗口和 CPU 调度都要在吞吐量、响应时间与公平性之间动态权衡。",
    ),
    (
        "kp_cn_cn_transport_08", "kp_os_os_process_04", "共享资源的流量整形",
        "发送窗口限制进入网络的数据量，调度器限制进入 CPU 的工作量，本质都是防止共享资源过载。",
    ),
    (
        "kp_co_co_cpu_03", "kp_os_os_process_07", "并发推进中的资源冲突",
        "流水线冒险与进程同步都要检测依赖，在资源未就绪时停顿、互锁或转发。",
    ),
    (
        "kp_co_co_cpu_08", "kp_os_os_sync_01", "并行度、冲突与有效吞吐",
        "提高并行度只有在冲突可控时才提升吞吐；结构冲突与临界区竞争都会制造等待。",
    ),
    (
        "kp_ds_ds_stack_queue_03", "kp_os_os_process_04", "队列作为调度状态容器",
        "就绪队列把数据结构中的入队、出队规则直接映射为进程等待与获得 CPU 的顺序。",
    ),
)


def enrich_cross_subject_relations(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(item.get("id") or ""): item for item in records if item.get("id")}
    curated: dict[str, list[dict[str, str]]] = defaultdict(list)
    for left, right, theme, explanation in CURATED_RELATIONS:
        if left not in by_id or right not in by_id:
            continue
        curated[left].append({"target_id": right, "theme": theme, "explanation": explanation})
        curated[right].append({"target_id": left, "theme": theme, "explanation": explanation})

    enriched: list[dict[str, Any]] = []
    for record in records:
        point_id = str(record.get("id") or "")
        relations = list(curated.get(point_id, []))
        target_ids = {item["target_id"] for item in relations}
        for target_id in map(str, record.get("cross_subject_point_ids") or []):
            if target_id in by_id and target_id not in target_ids:
                relations.append({
                    "target_id": target_id,
                    "theme": "跨学科机制关联",
                    "explanation": "从不同课程视角描述同一类系统机制，可对照定义、状态量与约束条件学习。",
                })
                target_ids.add(target_id)
        item = dict(record)
        item["cross_subject_point_ids"] = sorted(target_ids)
        item["cross_subject_relations"] = relations
        enriched.append(item)
    return enriched
