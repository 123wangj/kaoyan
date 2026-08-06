from __future__ import annotations

import re
import ipaddress
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VisualizationRule:
    category: str
    label: str
    template: str
    pattern: re.Pattern[str]


def _rule(category: str, label: str, template: str, pattern: str) -> VisualizationRule:
    return VisualizationRule(category, label, template, re.compile(pattern, re.I))


# Only strong, process-oriented signals belong here. Generic words such as “tree”,
# “network layer” or “cache” alone are intentionally excluded to avoid offering a
# diagram for a definition-only question.
RULES = (
    _rule("sorting", "排序过程", "sequence", r"冒泡排序|快速排序|归并排序|堆排序|插入排序|希尔排序|选择排序|排序趟|第[一二三四五六七八九\d]+趟排序"),
    _rule("tree", "树结构与遍历", "node-map", r"前序(?:遍历)?|中序(?:遍历)?|后序(?:遍历)?|层次遍历|哈夫曼树|Huffman|B\+?树|AVL|平衡二叉树|二叉排序树|线索二叉树"),
    _rule("graph", "图算法过程", "node-map", r"拓扑排序|关键路径|最短路径|Dijkstra|Floyd|Prim|Kruskal|广度优先(?:遍历)?|深度优先(?:遍历)?|\bBFS\b|\bDFS\b|最小生成树"),
    _rule("stack_queue", "栈与队列变化", "sequence", r"入栈|出栈|进栈|退栈|栈序列|循环队列.{0,30}(队头|队尾|front|rear)|队列.{0,20}(入队|出队)"),
    _rule("linked_list", "链表操作", "node-map", r"链表.{0,30}(插入|删除|逆置|合并|头插|尾插)|单链表.{0,30}(指针|结点|节点)|双链表.{0,30}(指针|结点|节点)"),
    _rule("scheduling", "进程调度时间线", "timeline", r"先来先服务|短作业优先|最短剩余时间|时间片轮转|优先级调度|\bFCFS\b|\bSJF\b|周转时间|带权周转时间"),
    _rule("page_replacement", "页面置换过程", "memory-grid", r"页面置换|缺页次数|缺页率|\bFIFO\b.{0,40}(页面|页框|页帧)|\bLRU\b.{0,40}(页面|页框|页帧)|\bOPT\b.{0,40}(页面|页框|页帧)"),
    _rule("address_translation", "地址转换拆解", "bitfield", r"虚拟地址.{0,50}物理地址|逻辑地址.{0,50}物理地址|页号.{0,40}页内偏移|段页式.{0,40}地址|页表.{0,40}(地址转换|物理块|页框)|\bTLB\b.{0,40}(地址|页表|命中)"),
    _rule("synchronization", "同步与互斥流程", "state-flow", r"信号量|\bPV\b操作|\bP\s*操作\b|\bV\s*操作\b|生产者.{0,20}消费者|读者.{0,20}写者|哲学家进餐"),
    _rule("deadlock", "资源分配与安全序列", "state-flow", r"银行家算法|安全序列|资源分配图|死锁检测|死锁避免|死锁预防"),
    _rule("cache_mapping", "Cache 地址映射", "bitfield", r"Cache.{0,60}(直接映射|组相联|全相联|标记位|组号|块内地址)|主存地址.{0,60}(标记|组号|块内)|缓存.{0,40}(映射|命中率)"),
    _rule("pipeline", "流水线时空图", "timeline", r"流水线.{0,60}(时钟周期|吞吐率|加速比|执行时间|数据冒险|控制冒险)|数据相关.{0,30}(流水|指令)|指令流水"),
    _rule("number_repr", "数值编码拆解", "bitfield", r"IEEE\s*754|补码.{0,50}(表示|运算|范围|溢出)|原码.{0,30}反码|浮点数.{0,50}(阶码|尾数|规格化)|移码.{0,30}(表示|运算)"),
    _rule("memory_chip", "存储器扩展与片选", "structure", r"存储器.{0,50}(字扩展|位扩展|字位扩展|芯片数|片选)|芯片.{0,40}(地址线|数据线|组成|扩展)|片选.{0,40}(地址|译码)"),
    _rule("datapath", "指令执行数据通路", "state-flow", r"数据通路|微程序.{0,40}(控制|执行|微指令)|微指令.{0,40}(字段|编码|地址)|指令周期.{0,40}(取指|间址|执行|中断)"),
    _rule("tcp_flow", "TCP 交互过程", "packet-flow", r"三次握手|四次挥手|TCP.{0,40}(序号|确认号|连接建立|连接释放)|慢开始|拥塞避免|拥塞窗口|滑动窗口.{0,30}(发送|接收|确认)"),
    _rule("subnet", "子网与前缀拆解", "bitfield", r"子网掩码|CIDR|最长前缀匹配|网络地址.{0,30}广播地址|划分子网|路由聚合"),
    _rule("fragmentation", "IP 分片过程", "packet-flow", r"IP分片|IP 分片|片偏移|MF位|DF位|MTU.{0,30}分片"),
    _rule("protocol_layers", "协议封装层次", "layer-stack", r"封装.{0,20}解封装|协议栈|报文段.{0,20}数据报.{0,20}帧|数据.{0,20}(传输层|网络层|数据链路层).{0,20}(首部|头部)"),
    _rule("ethernet", "链路传输过程", "packet-flow", r"CSMA/CD|CSMA/CA|以太网帧.{0,40}(发送|接收|字段)|MAC地址表.{0,30}(转发|学习)|生成树协议|冲突窗口|二进制指数退避"),
)


TOKEN_RE = re.compile(
    r"(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?|0x[0-9a-f]+|[01]{4,}|\b\d+(?:\.\d+)?(?:\s*(?:ms|ns|KB|MB|GB|B|位|页|块|帧|秒|次))?\b",
    re.I,
)
PROCESS_SIGNAL_RE = re.compile(
    r"求|计算|多少|序列|顺序|过程|变化|执行|访问|地址|经过|结果|应为|如何|操作时|发送|接收|分配|置换|调度|遍历|排序"
)
CONCEPT_ONLY_RE = re.compile(r"目的是|主要作用|作用是|优点(?:之一)?是|特点是|定义是|英文全称")


def _source_text(question: dict[str, Any]) -> str:
    points = question.get("knowledge_points") or []
    if not isinstance(points, list):
        points = [points]
    return " ".join([str(question.get("content") or ""), *map(str, points)])


def _match_rule(question: dict[str, Any]) -> VisualizationRule | None:
    explanation = str(question.get("explanation") or "").strip()
    answer = str(question.get("answer") or "").strip()
    if len(explanation) < 60 or not answer:
        return None
    content = str(question.get("content") or "")
    direct = next((rule for rule in RULES if rule.pattern.search(content)), None)
    if direct:
        return direct
    # Knowledge-point labels can recover terse exam stems such as “结果是多少”,
    # but only when the stem itself clearly asks for a process or calculation.
    if PROCESS_SIGNAL_RE.search(content):
        return next((rule for rule in RULES if rule.pattern.search(_source_text(question))), None)
    return None


def visualization_capability(question: dict[str, Any]) -> dict[str, Any] | None:
    rule = _match_rule(question)
    if not rule or len(_reasoning_steps(str(question.get("explanation") or ""))) < 2:
        return None
    simulation = _build_simulation(question, rule)
    if CONCEPT_ONLY_RE.search(str(question.get("content") or "")) and not simulation:
        return None
    return {
        "available": True,
        "category": rule.category,
        "label": rule.label,
        "template": rule.template,
        "mode": "simulation" if simulation else "walkthrough",
        "mode_label": "动态演算" if simulation else "步骤图解",
    }


def _clean_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#>`]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -：:；;")
    return text


def _reasoning_steps(explanation: str) -> list[str]:
    normalized = re.sub(r"\s+(?=\d+[.、])", "\n", explanation)
    normalized = re.sub(r"\s+(?=[（(]?[A-D][）).、])", "\n", normalized)
    pieces = re.split(r"\n+|(?<=[。！？；])\s*", normalized)
    steps: list[str] = []
    for piece in pieces:
        cleaned = _clean_markdown(piece)
        if len(cleaned) < 12 or cleaned in steps:
            continue
        steps.append(cleaned)
    return steps


def _concepts(question: dict[str, Any], rule: VisualizationRule) -> list[str]:
    points = question.get("knowledge_points") or []
    if not isinstance(points, list):
        points = [points]
    concepts = [_clean_markdown(str(item)) for item in points if str(item).strip()]
    canonical = {
        "sorting": ["初始序列", "比较", "交换/归并", "有序结果"],
        "tree": ["根结点", "左子树", "右子树", "访问次序"],
        "graph": ["起点", "候选结点", "边/权值", "访问结果"],
        "stack_queue": ["输入序列", "栈/队列", "操作", "输出序列"],
        "scheduling": ["到达", "就绪队列", "CPU 执行", "完成"],
        "page_replacement": ["访问序列", "页框", "命中", "缺页/置换"],
        "address_translation": ["页号/段号", "表项", "页框号", "页内偏移"],
        "synchronization": ["进程", "共享资源", "P 操作", "V 操作"],
        "deadlock": ["可用资源", "尚需资源", "试分配", "安全序列"],
        "cache_mapping": ["标记", "组号/行号", "块内地址", "命中判断"],
        "pipeline": ["取指", "译码", "执行", "访存", "写回"],
        "number_repr": ["符号位", "指数/数值位", "尾数", "结果"],
        "memory_chip": ["容量需求", "字扩展", "位扩展", "片选"],
        "datapath": ["取指", "译码", "控制信号", "数据流向"],
        "tcp_flow": ["发送端", "报文", "确认", "接收端"],
        "subnet": ["网络前缀", "主机位", "掩码", "地址范围"],
        "fragmentation": ["原始数据报", "MTU", "片偏移", "重组"],
        "protocol_layers": ["应用层", "传输层", "网络层", "链路层"],
        "ethernet": ["侦听信道", "发送", "冲突/确认", "退避/完成"],
    }.get(rule.category, ["已知条件", "规则", "推导", "结论"])
    for item in canonical:
        if item not in concepts:
            concepts.append(item)
    return concepts[:8]


def _options(question: dict[str, Any]) -> list[dict[str, Any]]:
    answer = str(question.get("answer") or "").strip().upper()
    result = []
    for option in question.get("options") or []:
        value = str(option).strip()
        match = re.match(r"([A-Z])[.、\s)]*(.*)", value, re.I)
        if not match:
            continue
        label, text = match.group(1).upper(), match.group(2).strip()
        result.append({"label": label, "text": text, "correct": label in answer})
    return result


def _extract_number_sequence(text: str, minimum: int = 4) -> list[int] | None:
    cleaned = re.sub(r"【\s*\d{4}[^】]*】", " ", text)
    groups = re.findall(r"-?\d+(?:\s*[,，、]\s*-?\d+){%d,}" % (minimum - 1), cleaned)
    candidates = [list(map(int, re.findall(r"-?\d+", group))) for group in groups]
    candidates = [item for item in candidates if minimum <= len(item) <= 40]
    return max(candidates, key=len) if candidates else None


def _sorting_algorithm(text: str) -> str | None:
    names = (
        ("bubble", r"冒泡排序"), ("insertion", r"(?:直接)?插入排序"),
        ("selection", r"(?:简单)?选择排序"), ("quick", r"快速排序"),
        ("merge", r"(?:二路)?归并排序"), ("heap", r"堆排序"),
    )
    return next((name for name, pattern in names if re.search(pattern, text)), None)


def _sorting_simulation(question: dict[str, Any]) -> dict[str, Any] | None:
    content = str(question.get("content") or "")
    values = _extract_number_sequence(content)
    algorithm = _sorting_algorithm(content)
    if not values or not algorithm:
        return None
    array = values[:]
    states = [{"values": array[:], "active": [], "sorted": [], "description": f"初始序列：{'，'.join(map(str, array))}"}]

    if algorithm == "bubble":
        for end in range(len(array) - 1, 0, -1):
            swapped = False
            for index in range(end):
                if array[index] > array[index + 1]:
                    array[index], array[index + 1] = array[index + 1], array[index]
                    swapped = True
            states.append({"values": array[:], "active": [end], "sorted": list(range(end, len(array))), "description": f"第 {len(states)} 趟：最大元素归位到位置 {end + 1}。"})
            if not swapped:
                break
    elif algorithm == "insertion":
        for index in range(1, len(array)):
            key, cursor = array[index], index - 1
            while cursor >= 0 and array[cursor] > key:
                array[cursor + 1] = array[cursor]
                cursor -= 1
            array[cursor + 1] = key
            states.append({"values": array[:], "active": [cursor + 1], "sorted": list(range(index + 1)), "description": f"插入 {key}：前 {index + 1} 个元素保持有序。"})
    elif algorithm == "selection":
        for index in range(len(array) - 1):
            minimum = min(range(index, len(array)), key=array.__getitem__)
            array[index], array[minimum] = array[minimum], array[index]
            states.append({"values": array[:], "active": [index, minimum], "sorted": list(range(index + 1)), "description": f"第 {index + 1} 趟：选择最小值 {array[index]} 放到位置 {index + 1}。"})
    elif algorithm == "quick":
        def partition(low: int, high: int) -> int:
            pivot, left, right = array[low], low, high
            while left < right:
                while left < right and array[right] >= pivot:
                    right -= 1
                array[left] = array[right]
                while left < right and array[left] <= pivot:
                    left += 1
                array[right] = array[left]
            array[left] = pivot
            states.append({"values": array[:], "active": [left], "sorted": [], "description": f"以 {pivot} 为枢轴完成一次划分，枢轴落在位置 {left + 1}。"})
            return left
        def quicksort(low: int, high: int) -> None:
            if low < high and len(states) < 18:
                pivot_index = partition(low, high)
                quicksort(low, pivot_index - 1)
                quicksort(pivot_index + 1, high)
        quicksort(0, len(array) - 1)
    elif algorithm == "merge":
        width = 1
        while width < len(array):
            for left in range(0, len(array), width * 2):
                middle, right = min(left + width, len(array)), min(left + width * 2, len(array))
                array[left:right] = sorted(array[left:right])
            states.append({"values": array[:], "active": [], "sorted": [], "description": f"归并长度为 {width} 的相邻有序段，得到长度至多 {width * 2} 的有序段。"})
            width *= 2
    else:  # heap
        def sift_down(root: int, end: int) -> None:
            while root * 2 + 1 <= end:
                child = root * 2 + 1
                if child + 1 <= end and array[child] < array[child + 1]:
                    child += 1
                if array[root] >= array[child]:
                    return
                array[root], array[child] = array[child], array[root]
                root = child
        for root in range(len(array) // 2 - 1, -1, -1):
            sift_down(root, len(array) - 1)
        states.append({"values": array[:], "active": [0], "sorted": [], "description": "从最后一个非叶结点开始调整，建立大根堆。"})
        for end in range(len(array) - 1, 0, -1):
            array[0], array[end] = array[end], array[0]
            sift_down(0, end - 1)
            states.append({"values": array[:], "active": [0, end], "sorted": list(range(end, len(array))), "description": f"取堆顶最大值 {array[end]} 放到位置 {end + 1}，再调整剩余堆。"})
            if len(states) >= 18:
                break
    if states[-1]["values"] != sorted(values):
        states.append({"values": sorted(values), "active": [], "sorted": list(range(len(values))), "description": "全部元素已有序。"})
    return {"kind": "sorting", "algorithm": algorithm, "original": values, "states": states[:18], "result": sorted(values)}


def _page_replacement_simulation(question: dict[str, Any]) -> dict[str, Any] | None:
    content = str(question.get("content") or "")
    references = _extract_number_sequence(content, 5)
    frame_match = re.search(r"(?:分配|给|有|为)\s*(\d+)\s*(?:个)?(?:页框|页帧|物理块|内存块)", content)
    algorithm_match = re.search(r"\b(FIFO|LRU|OPT)\b", content, re.I)
    if not references or not frame_match or not algorithm_match:
        return None
    frame_count = int(frame_match.group(1))
    if not 1 <= frame_count <= 8:
        return None
    algorithm = algorithm_match.group(1).upper()
    frames: list[int] = []
    ages: dict[int, int] = {}
    fifo_index = 0
    faults = 0
    states = []
    for step, page in enumerate(references):
        hit, evicted = page in frames, None
        if hit:
            ages[page] = step
        else:
            faults += 1
            if len(frames) < frame_count:
                frames.append(page)
            else:
                if algorithm == "FIFO":
                    victim_index = fifo_index % frame_count
                    fifo_index += 1
                elif algorithm == "LRU":
                    victim_index = min(range(len(frames)), key=lambda idx: ages.get(frames[idx], -1))
                else:
                    future = references[step + 1 :]
                    distances = [future.index(value) if value in future else 10**6 for value in frames]
                    victim_index = max(range(len(frames)), key=distances.__getitem__)
                evicted = frames[victim_index]
                frames[victim_index] = page
            ages[page] = step
        padded = frames[:] + [None] * (frame_count - len(frames))
        action = "命中，无需置换" if hit else (f"缺页，淘汰页面 {evicted}" if evicted is not None else "缺页，装入空闲页框")
        states.append({"reference": page, "frames": padded, "hit": hit, "evicted": evicted, "faults": faults, "description": f"访问页面 {page}：{action}。累计缺页 {faults} 次。"})
    return {"kind": "page_replacement", "algorithm": algorithm, "references": references, "frame_count": frame_count, "states": states, "faults": faults, "fault_rate": round(faults / len(references) * 100, 1)}


def _pipeline_simulation(question: dict[str, Any]) -> dict[str, Any] | None:
    content = str(question.get("content") or "")
    instruction_match = re.search(r"(\d+)\s*条指令", content)
    durations = [float(value) for value, _unit in re.findall(r"(?:=|为|分别是|,|，)\s*(\d+(?:\.\d+)?)\s*(ns|ms|μs|us)", content, re.I)]
    if not instruction_match or len(durations) < 2 or len(durations) > 8:
        return None
    instruction_count = int(instruction_match.group(1))
    if not 2 <= instruction_count <= 10000:
        return None
    stage_count = len(durations)
    default_names = ["取指", "译码", "执行", "访存", "写回"]
    names = default_names[:stage_count] if stage_count <= len(default_names) else [f"阶段 {i + 1}" for i in range(stage_count)]
    cycle, first_latency = max(durations), sum(durations)
    total = first_latency + (instruction_count - 1) * cycle
    rows = []
    for instruction in range(min(instruction_count, 6)):
        rows.append({"instruction": instruction + 1, "cells": [{"stage": names[index], "cycle": instruction + index} for index in range(stage_count)]})
    states = [
        {"description": f"各段耗时为 {'、'.join(_format_number(item) for item in durations)}，流水线周期取最大值 {_format_number(cycle)}。", "focus": "cycle"},
        {"description": f"第一条指令完整经过 {stage_count} 段，实际延迟为 {_format_number(first_latency)}。", "focus": "latency"},
        {"description": f"其余 {instruction_count - 1} 条每隔 {_format_number(cycle)} 完成一条，总时间为 {_format_number(first_latency)} + {instruction_count - 1} × {_format_number(cycle)} = {_format_number(total)}。", "focus": "total"},
    ]
    return {"kind": "pipeline", "durations": durations, "stages": names, "instruction_count": instruction_count, "cycle": cycle, "first_latency": first_latency, "total": total, "rows": rows, "states": states}


def _format_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 3))


def _subnet_simulation(question: dict[str, Any]) -> dict[str, Any] | None:
    sources = [str(question.get("content") or ""), *map(str, question.get("options") or [])]
    candidates = []
    answer = str(question.get("answer") or "").strip().upper()
    for source in sources:
        normalized = re.sub(r"\s*\.\s*", ".", source)
        label_match = re.match(r"\s*([A-D])[.、\s)]", normalized, re.I)
        for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d{1,3}){3})(?:/(\d{1,2}))?", normalized):
            ip_text, prefix_text = match.group(1), match.group(2)
            octets = list(map(int, ip_text.split(".")))
            canonical_ip = ".".join(map(str, octets))
            label = label_match.group(1).upper() if label_match else ""
            if any(item > 255 for item in octets):
                candidates.append({"label": label, "ip": ip_text, "valid": False, "reason": "存在超过 255 的字段，IP 地址格式非法。", "correct_option": label in answer})
                continue
            first = octets[0]
            prefix = int(prefix_text) if prefix_text else (8 if 1 <= first <= 126 else 16 if 128 <= first <= 191 else 24 if 192 <= first <= 223 else None)
            if prefix is None or prefix > 32 or first == 127:
                reason = "127/8 为环回地址，不能分配给互联网主机。" if first == 127 else "不属于可分配的 A/B/C 类单播地址。"
                candidates.append({"label": label, "ip": ip_text, "valid": False, "reason": reason, "correct_option": label in answer})
                continue
            network = ipaddress.ip_network(f"{canonical_ip}/{prefix}", strict=False)
            address = ipaddress.ip_address(canonical_ip)
            valid = address not in (network.network_address, network.broadcast_address)
            reason = "主机位既不全 0 也不全 1，可以分配给主机。" if valid else ("主机位全 0，是网络地址。" if address == network.network_address else "主机位全 1，是广播地址。")
            candidates.append({
                "label": label, "ip": canonical_ip, "prefix": prefix,
                "bits": [format(item, "08b") for item in octets],
                "network": str(network.network_address), "broadcast": str(network.broadcast_address),
                "valid": valid, "reason": reason, "correct_option": label in answer,
            })
    unique = []
    for item in candidates:
        if not any(existing["ip"] == item["ip"] for existing in unique):
            unique.append(item)
    if not unique:
        return None
    states = [{"candidate_index": index, "description": f"检查 {item['label'] + '：' if item['label'] else ''}{item['ip']}：{item['reason']}"} for index, item in enumerate(unique)]
    return {"kind": "subnet", "candidates": unique, "states": states}


def _linked_list_simulation(question: dict[str, Any]) -> dict[str, Any] | None:
    content = str(question.get("content") or "")
    if not re.search(r"(?:增加|设置|带有?|引入).{0,8}头结点|头结点.{0,8}(?:目的|作用)", content):
        return None
    states = [
        {
            "variant": "without_head",
            "description": "不带头结点时，head 直接指向首元结点；空表时 head=NULL，首部操作必须单独判断。",
        },
        {
            "variant": "with_head",
            "description": "增加头结点后，head 始终指向固定的 HEAD；空表只需令 HEAD.next=NULL。",
        },
        {
            "variant": "uniform_operation",
            "description": "在首部插入或删除时，HEAD 就是首元结点的稳定前驱，操作与链表中间位置完全一致。",
        },
    ]
    return {
        "kind": "linked_list_head",
        "states": states,
        "result": "头结点统一了空表与非空表、首部与中间位置的边界处理，从而方便运算实现。",
    }


def _build_simulation(question: dict[str, Any], rule: VisualizationRule) -> dict[str, Any] | None:
    builders = {
        "sorting": _sorting_simulation,
        "linked_list": _linked_list_simulation,
        "page_replacement": _page_replacement_simulation,
        "pipeline": _pipeline_simulation,
        "subnet": _subnet_simulation,
    }
    builder = builders.get(rule.category)
    return builder(question) if builder else None


def infer_error_focus(spec: dict[str, Any], selected_option: str | None) -> dict[str, Any] | None:
    """Locate the most useful replay checkpoint from a wrong multiple-choice answer.

    A choice-only answer cannot prove the student's exact intermediate mistake, so
    the result is explicitly marked as inferred. When the option exposes a numeric
    result or a concrete candidate, we map that evidence back to a deterministic
    simulation state instead of sending the learner to a generic animation.
    """
    selected = str(selected_option or "").strip().upper()[:1]
    options = spec.get("options") or []
    selected_item = next((item for item in options if item.get("label") == selected), None)
    if not selected_item or selected_item.get("correct"):
        return None
    simulation = spec.get("simulation") or {}
    states = simulation.get("states") or []
    if not states:
        return {
            "step": 0,
            "confidence": "inferred",
            "reason": "从解析第一步开始，对照所选项与标准推导的分歧。",
        }

    kind = simulation.get("kind")
    option_numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", str(selected_item.get("text") or ""))]
    step = 0
    reason = "从第一个关键状态重新核对题干条件与算法规则。"

    if kind == "page_replacement" and option_numbers:
        claimed = int(option_numbers[0])
        actual = int(simulation.get("faults") or 0)
        if claimed < actual:
            step = next((index for index, state in enumerate(states) if int(state.get("faults") or 0) > claimed), len(states) - 1)
            reason = f"你选择的结果只累计 {claimed} 次缺页；标准演算在此处出现第 {claimed + 1} 次缺页。"
        elif claimed > actual:
            step = next((index for index, state in enumerate(states) if state.get("hit") is True), max(0, len(states) - 1))
            reason = f"你选择的缺页数比标准结果多 {claimed - actual} 次；优先核对这里的命中是否被误算成缺页。"
    elif kind == "sorting" and option_numbers:
        claimed_values = [int(value) for value in option_numbers]
        step = next((index for index, state in enumerate(states) if state.get("values") == claimed_values), 1 if len(states) > 1 else 0)
        reason = "所选序列对应或接近这一轮状态；从本轮的比较、交换边界开始核对。"
    elif kind == "subnet":
        step = next((index for index, item in enumerate(simulation.get("candidates") or []) if item.get("label") == selected), 0)
        reason = f"直接定位到你选择的 {selected} 项，重新核对网络位、主机位和地址合法性。"
    elif kind == "pipeline" and option_numbers:
        claimed = option_numbers[0]
        checkpoints = [simulation.get("cycle"), simulation.get("first_latency"), simulation.get("total")]
        step = min(range(len(checkpoints)), key=lambda index: abs(float(checkpoints[index] or 0) - claimed))
        reason = "从与所选数值最接近的计算阶段开始，核对周期、首条延迟和总时间是否混用。"
    else:
        step = min(max(0, ord(selected) - ord("A")), len(states) - 1)

    return {
        "step": max(0, min(step, len(states) - 1)),
        "confidence": "inferred",
        "selected_option": selected,
        "reason": reason,
    }


def build_question_visualization(question: dict[str, Any]) -> dict[str, Any] | None:
    rule = _match_rule(question)
    if not rule:
        return None
    explanation = str(question.get("explanation") or "")
    steps = _reasoning_steps(explanation)
    if len(steps) < 2:
        return None
    content = str(question.get("content") or "")
    tokens = []
    for token in TOKEN_RE.findall(content):
        token = token.strip()
        if token and token not in tokens:
            tokens.append(token)
    simulation = _build_simulation(question, rule)
    if CONCEPT_ONLY_RE.search(content) and not simulation:
        return None
    if simulation:
        steps = [state["description"] for state in simulation.get("states", [])]
    return {
        "question_id": str(question.get("id") or ""),
        "title": rule.label,
        "category": rule.category,
        "template": rule.template,
        "subject": str(question.get("subject") or ""),
        "answer": str(question.get("answer") or ""),
        "concepts": _concepts(question, rule),
        "tokens": tokens[:12],
        "steps": steps,
        "options": _options(question),
        "mode": "simulation" if simulation else "walkthrough",
        "mode_label": "动态演算" if simulation else "步骤图解",
        "simulation": simulation,
        "full_explanation": explanation,
        "notice": "本图由题干数据按算法规则实时演算，可逐步核对中间状态。" if simulation else "本题暂未提取出可验证的演算数据，仅展示解析结构；标准答案与完整解析仍以题库内容为准。",
    }
