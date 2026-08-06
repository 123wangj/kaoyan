from __future__ import annotations

import re
from typing import Any


PROCESS_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (r"排序|冒泡|快速|归并|插入|选择|希尔|堆排序", "sequence", ("读取初始序列", "按算法规则比较", "交换或归并", "得到有序结果")),
    (r"栈|队列|链表|顺序表", "state", ("读取当前结构", "执行插入/删除操作", "更新指针或下标", "检查边界与结果")),
    (r"二叉树|树的遍历|哈夫曼|AVL|平衡二叉|B\+?树", "tree", ("确定根结点", "处理左侧结构", "处理右侧结构", "按规则输出或调整")),
    (r"图的遍历|最短路径|Dijkstra|Floyd|Prim|Kruskal|拓扑|关键路径", "graph", ("确定起点与候选集合", "选择下一结点或边", "更新距离/入度/集合", "形成最终路径或序列")),
    (r"进程状态|进程调度|处理机调度|作业调度|时间片|先来先服务|短作业|优先级", "timeline", ("进程到达", "进入就绪队列", "调度器选择进程", "运行并完成或重新排队")),
    (r"信号量|PV操作|同步|互斥|生产者|消费者|读者|写者|哲学家", "state", ("检查共享资源状态", "执行 P 操作申请", "进入临界区或阻塞", "执行 V 操作释放并唤醒")),
    (r"死锁|银行家|安全序列|资源分配", "resource", ("计算可用与尚需资源", "寻找可满足进程", "模拟完成并释放资源", "判断安全状态")),
    (r"分页|分段|页表|TLB|地址变换|页面置换|虚拟内存", "memory", ("拆分逻辑地址", "查询 TLB/页表", "处理命中或缺页", "组合物理地址")),
    (r"流水线|指令周期|数据通路|微程序|微指令", "timeline", ("取指", "译码与控制", "执行/访存", "写回并推进下一条指令")),
    (r"Cache|缓存|组相联|直接映射|全相联|存储层次", "memory", ("按块大小拆分地址", "计算 Cache 组/行", "比较标记判断命中", "装入或替换 Cache 块")),
    (r"补码|原码|反码|浮点|IEEE|移码|定点数", "bitfield", ("确定符号与位宽", "转换数值字段", "执行规格化或补码变换", "组合最终机器数")),
    (r"TCP|三次握手|四次挥手|滑动窗口|拥塞|可靠传输", "packet", ("发送端构造报文", "接收端检查序号", "返回确认或调整窗口", "推进连接/传输状态")),
    (r"IP地址|子网|CIDR|路由|最长前缀|IP分片", "bitfield", ("转换地址与掩码", "划分网络位和主机位", "计算地址范围/下一跳", "检查合法性并得出结果")),
    (r"封装|协议栈|OSI|体系结构|各层协议", "layers", ("应用数据产生", "逐层添加首部", "链路上传输", "接收端逐层解封装")),
)


SIMULATOR_RULES: tuple[tuple[str, str, str, dict[str, Any]], ...] = (
    (r"冒泡排序|快速排序|归并排序|插入排序|选择排序|希尔排序|堆排序|排序算法", "sorting", "排序算法实验室", {"sequence": "49,38,65,97,76,13,27,49", "algorithm": "bubble"}),
    (r"页面置换|FIFO.*页面|LRU.*页面|OPT.*页面", "page_replacement", "页面置换实验室", {"references": "7,0,1,2,0,3,0,4,2,3", "frames": 3, "algorithm": "LRU"}),
    (r"进程调度|处理机调度|作业调度|时间片轮转|先来先服务|短作业优先", "scheduling", "进程调度实验室", {"bursts": "3,6,4,5", "algorithm": "SJF", "quantum": 2}),
    (r"Cache.*映射|直接映射|组相联|全相联|Cache地址|Cache总容量|Cache容量配置", "cache", "Cache 映射计算器", {"address": 2593, "lines": 64, "ways": 4, "block_size": 32}),
    (r"补码|原码与反码|定点数表示|移码", "number", "机器数转换器", {"value": -66, "bits": 8, "encoding": "complement"}),
    (r"IP地址|子网划分|子网掩码|CIDR|网络地址|广播地址", "subnet", "子网划分实验室", {"ip": "192.168.10.70", "prefix": 26}),
    (r"指令流水线|流水线技术|流水线性能", "pipeline", "指令流水线实验室", {"durations": "2,2,1", "instructions": 10}),
    (r"栈.*基本操作|队列.*基本操作|循环队列|栈和队列|栈与|队列与|共享栈|双端队列|链式队列", "stack_queue", "栈与队列操作实验室", {"values": "A,B,C,D", "structure": "stack"}),
)


CONFUSION_PAIRS: tuple[tuple[str, str], ...] = (
    ("逻辑结构", "存储结构"), ("算法", "程序"), ("栈", "队列"),
    ("顺序表", "链表"), ("前序遍历", "中序遍历"), ("进程", "线程"),
    ("并发", "并行"), ("同步", "互斥"), ("分页", "分段"),
    ("Cache", "TLB"), ("原码", "补码"), ("TCP", "UDP"),
    ("网络地址", "广播地址"), ("电路交换", "分组交换"),
)


PROCESS_CHECKPOINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "sequence": (
        ("当前有序区在哪里？", "先指出已经确定有序的区间，再判断下一次比较。"),
        ("这一步比较的两个对象是谁？", "只比较算法规则指定的关键字，不要凭最终大小关系跳步。"),
        ("交换或移动后，哪个性质保持不变？", "已经形成的有序区仍然有序。"),
        ("如何验证结果？", "检查整体单调性，并核对元素个数与原序列一致。"),
    ),
    "memory": (
        ("地址或访问序列先拆成什么？", "先确定块号/页号与块内/页内偏移。"),
        ("本次访问命中了哪一级？", "按 TLB、页表或 Cache 的实际查找顺序判断。"),
        ("未命中时必须发生替换吗？", "不一定；仍有空闲位置时可直接装入。"),
        ("最终结果中哪一部分不会改变？", "地址变换时页内或块内偏移保持不变。"),
    ),
    "packet": (
        ("发送端此刻掌握哪些状态量？", "重点看序号、确认号、窗口和连接状态。"),
        ("接收端凭什么接受或丢弃？", "依据序号范围、校验与当前窗口判断。"),
        ("确认号表示已经收到哪一段？", "确认号通常表示下一次期望收到的序号。"),
        ("状态推进的触发条件是什么？", "收到合法报文或定时器超时才会推进。"),
    ),
    "timeline": (
        ("谁已经到达，谁仍不可选？", "只从当前时刻已到达的候选中选择。"),
        ("当前规则优先比较哪个量？", "根据算法比较到达时间、服务时间或优先级。"),
        ("何时发生抢占或重新排队？", "时间片耗尽或更高优先级任务到达时。"),
        ("最终指标如何计算？", "周转时间=完成时间−到达时间，等待时间=周转−服务。"),
    ),
    "bitfield": (
        ("总位宽是多少？", "先固定总位数，再划分字段，避免少算或多算一位。"),
        ("字段边界由哪个参数决定？", "前缀、块大小或编码规格决定边界。"),
        ("这一步是数值运算还是位模式解释？", "先区分数值与编码，负数补码不能直接按无符号数解释。"),
        ("怎样反向校验？", "把结果重新解码或代回原公式。"),
    ),
}


SIMULATOR_CHALLENGES: dict[str, str] = {
    "sorting": "先预测：把序列改成基本有序后，哪种算法的比较或移动会明显减少？",
    "page_replacement": "先预测：增加一个页框后缺页次数一定减少吗？分别用 FIFO 与 LRU 验证。",
    "scheduling": "先预测：SJF 为什么通常降低平均等待时间，却可能让长作业饥饿？",
    "cache": "先预测：块大小翻倍后，偏移位数和组号会怎样变化？",
    "number": "先预测：同一位模式按有符号数和无符号数解释时，数值差多少？",
    "subnet": "先预测：前缀长度增加 1，可用主机数大约发生什么变化？",
    "pipeline": "先预测：只缩短非瓶颈流水段，流水周期是否一定缩短？",
    "stack_queue": "先预测：相同输入依次进入栈和队列，输出顺序为什么相反？",
}


def _first_sentence(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    parts = re.split(r"(?<=[。！？；])", value, maxsplit=1)
    return parts[0].strip() if parts else value


def _markdown_section(text: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}\*\*[:：]\s*(.*?)(?=\n\s*\n\*\*|$)", str(text or ""), re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def _learning_check(point: dict[str, Any], related_questions: list[dict[str, Any]]) -> dict[str, Any] | None:
    curated = (point.get("exam_questions") or [])[:1]
    source = curated[0] if curated else (related_questions[0] if related_questions else None)
    if not source:
        key_points = [str(item) for item in (point.get("score_points") or point.get("tags") or []) if str(item).strip()]
        return {
            "stem": f"不看资料，用自己的话说明“{point.get('title') or '该知识点'}”最关键的一条规则。",
            "options": [],
            "answer": key_points[0] if key_points else _first_sentence(str(point.get("content") or "")),
            "analysis": "先说适用对象，再说规则，最后补充一个边界条件或常见错误。",
            "year": None,
        }
    return {
        "stem": str(source.get("stem") or source.get("content") or ""),
        "options": [str(item) for item in (source.get("options") or [])],
        "answer": str(source.get("answer") or ""),
        "analysis": str(source.get("analysis") or source.get("explanation") or ""),
        "year": source.get("year"),
    }


def _resolve_titles(ids: list[Any], records_by_id: dict[str, dict]) -> list[dict[str, str]]:
    items = []
    for point_id in ids or []:
        record = records_by_id.get(str(point_id))
        if record:
            items.append({"id": str(point_id), "title": str(record.get("title") or point_id), "subject": str(record.get("subject") or "")})
    return items


def _resolve_cross_subject_relations(point: dict[str, Any], records_by_id: dict[str, dict]) -> list[dict[str, str]]:
    resolved = []
    details = point.get("cross_subject_relations") or []
    for relation in details:
        target_id = str(relation.get("target_id") or "")
        target = records_by_id.get(target_id)
        if not target:
            continue
        resolved.append({
            "id": target_id,
            "title": str(target.get("title") or target_id),
            "subject": str(target.get("subject") or ""),
            "theme": str(relation.get("theme") or "跨学科机制关联"),
            "explanation": str(relation.get("explanation") or ""),
        })
    if resolved:
        return resolved
    return [
        {**item, "theme": "跨学科机制关联", "explanation": "从不同课程视角对照理解同一类机制。"}
        for item in _resolve_titles(point.get("cross_subject_point_ids") or [], records_by_id)
    ]


def _process_spec(point: dict[str, Any]) -> dict[str, Any]:
    # Capability is mapped from catalog metadata, not loose words buried in a
    # long explanation. This keeps process animations for genuine mechanisms.
    source = " ".join(map(str, [point.get("title", ""), point.get("knowledge_points", []), point.get("tags", [])]))
    for pattern, kind, stages in PROCESS_RULES:
        if re.search(pattern, source, re.I):
            checks = PROCESS_CHECKPOINTS.get(kind) or (
                ("这一步的输入是什么？", "先明确输入对象和当前状态。"),
                ("状态发生了什么变化？", "只记录本步规则直接造成的变化。"),
                ("下一步为什么可以执行？", "检查前置条件是否已经满足。"),
                ("如何验证最终结果？", "用定义、边界条件或反向计算复核。"),
            )
            enriched = []
            for index, title in enumerate(stages):
                question, answer = checks[min(index, len(checks) - 1)]
                enriched.append({
                    "index": index + 1,
                    "title": title,
                    "input": "题目给出的初始条件" if index == 0 else f"上一步“{stages[index - 1]}”的结果",
                    "output": "可用于最终作答的结论" if index == len(stages) - 1 else f"进入“{stages[index + 1]}”所需的新状态",
                    "question": question,
                    "answer": answer,
                })
            return {"available": True, "kind": kind, "stages": enriched}
    return {"available": False, "kind": "concept", "stages": []}


def _simulator_spec(point: dict[str, Any]) -> dict[str, Any]:
    source = " ".join(map(str, [point.get("title", ""), point.get("knowledge_points", []), point.get("tags", [])]))
    for pattern, simulator_type, title, defaults in SIMULATOR_RULES:
        if re.search(pattern, source, re.I):
            return {
                "available": True, "type": simulator_type, "title": title,
                "defaults": defaults, "challenge": SIMULATOR_CHALLENGES[simulator_type],
            }
    return {"available": False, "type": "", "title": "", "defaults": {}}


def build_knowledge_visualization(
    point: dict[str, Any],
    all_points: list[dict[str, Any]],
    questions: list[dict[str, Any]],
    learning_state: dict[str, Any],
    completion: dict[str, Any],
) -> dict[str, Any]:
    records_by_id = {str(item.get("id")): item for item in all_points if item.get("id")}
    title = str(point.get("title") or "")
    point_id = str(point.get("id") or "")
    subject = str(point.get("subject") or "")
    aliases = {title, *map(str, point.get("knowledge_points") or [])}
    related_questions = [
        question for question in questions
        if (
            aliases.intersection(map(str, question.get("knowledge_points") or []))
            or point_id in set(map(str, question.get("knowledge_point_ids") or []))
        )
    ]
    wrong_ids = {
        str(item.get("question_id") or item.get("id") or "")
        for item in learning_state.get("wrong_questions", [])
        if (
            aliases.intersection(map(str, item.get("knowledge_points") or []))
            or point_id in set(map(str, item.get("knowledge_point_ids") or []))
        )
    }
    mastery = (completion.get("knowledge_points") or {}).get(title) or {}
    score = float(mastery.get("progress") or 0)
    process = _process_spec(point)
    simulator = _simulator_spec(point)
    score_points = [str(item) for item in (point.get("score_points") or []) if str(item).strip()]
    learning_items = score_points or [str(item) for item in (point.get("tags") or []) if str(item).strip()]
    confusion = [
        {"left": left, "right": right}
        for left, right in CONFUSION_PAIRS
        if left in str(point.get("content") or "") and right in str(point.get("content") or "")
    ][:4]
    if not confusion:
        related_titles = _resolve_titles(point.get("related_point_ids") or [], records_by_id)
        confusion = [{"left": title, "right": item["title"]} for item in related_titles[:2]]
    recommendation = (
        "先完成结构梳理，再进入模拟器改变参数，并重做错题。"
        if simulator["available"] and wrong_ids
        else "先按过程演示逐步复述，再完成关联真题。"
        if process["available"]
        else "先掌握定义和易混关系，再通过关联真题检验理解。"
    )
    explanation = str(point.get("detailed_explanation") or "")
    analogy = _markdown_section(explanation, "生活类比")
    common_trap = _markdown_section(explanation, "易错提醒")
    exam_direction = _markdown_section(explanation, "真题方向")
    learning_check = _learning_check(point, related_questions)
    return {
        "point": {
            "id": str(point.get("id") or ""), "title": title, "subject": subject,
            "chapter_id": str(point.get("chapter_id") or ""), "chapter_title": str(point.get("chapter_title") or ""),
            "difficulty": str(point.get("difficulty") or ""), "importance": str(point.get("importance") or ""),
        },
        "structure": {
            "definition": _first_sentence(str(point.get("content") or "")),
            "components": score_points[:8] or [str(item) for item in (point.get("tags") or [])[:8]],
            "prerequisites": _resolve_titles(point.get("prerequisite_ids") or [], records_by_id),
            "related": _resolve_titles(point.get("related_point_ids") or [], records_by_id),
            "cross_subject": _resolve_cross_subject_relations(point, records_by_id),
            "confusions": confusion,
            "analogy": analogy,
            "common_trap": common_trap,
            "exam_direction": exam_direction,
        },
        "learning_mission": {
            "goals": [f"能够解释：{item}" for item in learning_items[:3]],
            "check": learning_check,
            "success_criteria": [
                "不用看资料，能用自己的话复述核心定义",
                "能指出至少一个适用条件或常见陷阱",
                "能独立完成一道关联题并解释错误选项",
            ],
        },
        "process": process,
        "simulator": simulator,
        "personalization": {
            "mastery_score": round(score, 1),
            "attempted": int(mastery.get("attempted") or 0),
            "total_questions": int(mastery.get("total") or len(related_questions)),
            "wrong_count": len(wrong_ids),
            "recommendation": recommendation,
            "questions": [
                {
                    "id": str(question.get("id") or ""), "content": str(question.get("content") or ""),
                    "year": question.get("year"), "subject": question.get("subject"), "type": question.get("type"),
                    "options": question.get("options") or [], "answer": question.get("answer"),
                    "explanation": question.get("explanation"), "source": question.get("source"),
                    "knowledge_points": question.get("knowledge_points") or [],
                    "is_wrong": str(question.get("id") or "") in wrong_ids,
                }
                for question in related_questions[:12]
            ],
        },
    }
