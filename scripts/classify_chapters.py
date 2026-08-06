import json
import re
from pathlib import Path

DATA = Path("data")

# ============================================================
# 章节定义与关键词库
# ============================================================

CHAPTERS = {
    "数据结构": [
        {
            "id": "ds_intro",
            "title": "绪论与线性表基础",
            "order": 1,
            "keywords": ["绪论", "数据结构", "逻辑结构", "物理结构", "存储结构", "抽象数据类型", "算法", "时间复杂度", "空间复杂度", "渐近", "大O", "大Ω", "大Θ"]
        },
        {
            "id": "ds_list",
            "title": "线性表",
            "order": 2,
            "keywords": ["线性表", "顺序表", "链表", "单链表", "双链表", "循环链表", "静态链表", "顺序存储", "链式存储", "插入", "删除", "头插", "尾插", "前驱", "后继"]
        },
        {
            "id": "ds_stack_queue",
            "title": "栈、队列和数组",
            "order": 3,
            "keywords": ["栈", "队列", "循环队列", "链栈", "链队列", "双端队列", "优先队列", "数组", "矩阵", "稀疏矩阵", "压缩存储", "对称矩阵", "三角矩阵", "三对角", "栈顶", "栈底", "入栈", "出栈", "进栈", "队首", "队尾", "入队", "出队"]
        },
        {
            "id": "ds_string",
            "title": "串",
            "order": 4,
            "keywords": ["串", "字符串", "子串", "模式匹配", "KMP", "next数组", "BF算法"]
        },
        {
            "id": "ds_tree",
            "title": "树与二叉树",
            "order": 5,
            "keywords": ["树", "二叉树", "完全二叉树", "满二叉树", "二叉排序树", "BST", "平衡二叉树", "AVL", "哈夫曼", "霍夫曼", "Huffman", "二叉搜索树", "二叉查找树", "红黑树", "红叔", "B树", "B-树", "B+树", "二叉树的遍历", "先序", "中序", "后序", "层次遍历", "前序", "线索二叉树", "森林", "树转二叉树", "并查集", "堆", "大根堆", "小根堆", "堆排序", "结点", "叶子", "分支结点", "度", "深度", "高度"]
        },
        {
            "id": "ds_graph",
            "title": "图",
            "order": 6,
            "keywords": ["图", "有向图", "无向图", "连通图", "强连通", "邻接矩阵", "邻接表", "深度优先", "广度优先", "DFS", "BFS", "最小生成树", "Prim", "Kruskal", "最短路径", "Dijkstra", "Floyd", "拓扑排序", "关键路径", "AOV", "AOE", "入度", "出度", "权", "网"]
        },
        {
            "id": "ds_search",
            "title": "查找",
            "order": 7,
            "keywords": ["查找", "搜索", "二分查找", "折半查找", "哈希", "散列", "冲突", "装填因子", "ASL", "顺序查找", "分块查找", "二叉排序树", "平衡二叉树", "B树", "B+树", "红黑树", "索引", "平均查找长度"]
        },
        {
            "id": "ds_sort",
            "title": "排序",
            "order": 8,
            "keywords": ["排序", "冒泡", "插入", "选择", "快速排序", "归并", "基数排序", "桶排序", "希尔排序", "堆排序", "直接插入", "简单选择", "外部排序", "稳定", "不稳定", "内排序", "外排序", "多路归并", "置换选择"]
        },
    ],
    "计算机组成原理": [
        {
            "id": "co_overview",
            "title": "计算机系统概述",
            "order": 1,
            "keywords": ["计算机发展", "冯诺依曼", "存储程序", "计算机系统", "硬件", "软件", "系统软件", "应用软件", "CPU", "主存", "I/O", "IO", "总线", "吞吐量", "响应时间", "MIPS", "MFLOPS", "CPI", "主频", "时钟", "字长", "机器字长", "指令字长", "存储字长", "数据字长", "MDR", "MAR", "兼容", "层次结构", "Amdahl"]
        },
        {
            "id": "co_data",
            "title": "数据的表示和运算",
            "order": 2,
            "keywords": ["原码", "反码", "补码", "移码", "定点", "浮点", "IEEE", "754", "溢出", "进位", "移位", "算术移位", "逻辑移位", "循环移位", "加法", "减法", "乘法", "除法", "ALU", "加法器", "串行", "并行", "标志", "OF", "SF", "ZF", "CF", "符号扩展", "位扩展", "数据表示", "运算", "浮点数", "规格化"]
        },
        {
            "id": "co_memory",
            "title": "存储系统",
            "order": 3,
            "keywords": ["存储器", "存储", "主存", "内存", "外存", "Cache", "缓存", "TLB", "页表", "页", "分页", "分段", "段页", "虚拟存储器", "虚拟地址", "物理地址", "快表", "慢表", "命中", "缺失", "替换", "LRU", "FIFO", "随机", "全相联", "组相联", "直接映射", "标记", "有效位", "脏位", "写回", "写直达", "ROM", "RAM", "SRAM", "DRAM", "SDRAM", "DDR", "芯片", "地址线", "数据线", "存储周期", "存取时间", "带宽", "交叉", "多体", "局部性", "空间局部性", "时间局部性", "读出数据", "写入数据"]
        },
        {
            "id": "co_instruction",
            "title": "指令系统",
            "order": 4,
            "keywords": ["指令", "指令格式", "操作码", "地址码", "定长", "变长", "扩展", "寻址", "立即", "直接", "间接", "寄存器", "基址", "变址", "相对", "CISC", "RISC", "复杂指令", "精简指令", "机器码", "汇编", "操作数"]
        },
        {
            "id": "co_cpu",
            "title": "中央处理器",
            "order": 5,
            "keywords": ["CPU", "控制器", "运算器", "数据通路", "硬布线", "微程序", "微指令", "微操作", "微命令", "微地址", "控制存储器", "uPC", "uMAR", "uIR", "uMDR", "控制单元", "CU", "PC", "IR", "PSW", "状态寄存器", "通用寄存器", "流水线", "冒险", "冲突", "数据相关", "控制相关", "结构相关", "转发", "旁路", "暂停", "分支预测", "超标量", "超流水", "多发射", "乱序", "顺序", "指令周期", "机器周期", "时钟周期", "取指", "间址", "执行", "中断", "断点", "栈顶", "堆栈", "SP", "微程序", "微指令", "微操作", "同步", "异步"]
        },
        {
            "id": "co_bus",
            "title": "总线",
            "order": 6,
            "keywords": ["总线", "系统总线", "数据总线", "地址总线", "控制总线", "ISA", "EISA", "PCI", "AGP", "USB", "串行", "并行", "同步", "异步", "仲裁", "集中", "分布", "链式", "计数器", "独立请求", "带宽", "工作频率", "猝发", "突发", "桥", "引脚", "金属引脚", "供电引脚"]
        },
        {
            "id": "co_io",
            "title": "输入输出系统",
            "order": 7,
            "keywords": ["输入", "输出", "I/O", "IO", "外设", "接口", "中断", "DMA", "通道", "程序查询", "程序中断", "直接存储器", "中断源", "中断屏蔽", "中断响应", "中断处理", "向量", "中断向量", "中断服务", "多重中断", "中断优先级", "隐指令", "中断周期", "磁盘", "硬盘", "磁道", "扇区", "柱面", "寻道", "旋转", "等待时间", "传输时间", "RAID", "显示器", "键盘", "打印机", "鼠标", "扫描仪", "打印质量", "打印速度", "机械结构", "色带", "传感器"]
        },
    ],
    "计算机网络": [
        {
            "id": "cn_overview",
            "title": "计算机网络体系结构",
            "order": 1,
            "keywords": ["计算机网络", "网络", "互联网", "Internet", "ISO", "OSI", "TCP/IP", "协议", "层次", "接口", "服务", "PDU", "SDU", "IDU", "面向连接", "无连接", "电路交换", "报文交换", "分组交换", "时延", "带宽", "吞吐量", "RTT", "利用率", "体系结构", "五层", "七层", "四层"]
        },
        {
            "id": "cn_physical",
            "title": "物理层",
            "order": 2,
            "keywords": ["物理层", "信号", "码元", "波特", "比特率", "波特率", "奈氏", "奈奎斯特", "香农", "信噪比", "信宿", "信源", "信道", "单工", "半双工", "全双工", "基带", "宽带", "调制", "解调", "编码", "曼彻斯特", "差分曼彻斯特", "NRZ", "4B/5B", "交换", "中继器", "集线器", "Hub", "Repeater", "机械特性", "电气特性", "功能特性"]
        },
        {
            "id": "cn_datalink",
            "title": "数据链路层",
            "order": 3,
            "keywords": ["数据链路", "成帧", "帧定界", "透明传输", "差错控制", "检错", "纠错", "CRC", "循环冗余", "海明", "流量控制", "滑动窗口", "后退N帧", "GBN", "选择重传", "SR", "停等", "CSMA", "CSMA/CD", "CSMA/CA", "ALOHA", "以太网", "MAC", "网卡", "交换机", "网桥", "VLAN", "PPP", "HDLC", "碰撞", "冲突", "最小帧长", "最大帧长", "二进制指数", "退避", "自学习", "生成树", "STP", "VLAN"]
        },
        {
            "id": "cn_network",
            "title": "网络层",
            "order": 4,
            "keywords": ["网络层", "IP", "IPv4", "IPv6", "路由器", "路由", "转发", "ARP", "ICMP", "IGMP", "子网", "子网掩码", "CIDR", "NAT", "VPN", "RIP", "OSPF", "BGP", "距离向量", "链路状态", "Dijkstra", "组播", "广播", "单播", "TTL", "分片", "路由表", "自治系统", "AS", "DHCP"]
        },
        {
            "id": "cn_transport",
            "title": "传输层",
            "order": 5,
            "keywords": ["传输层", "TCP", "UDP", "端口", "套接字", "socket", "连接", "三次握手", "四次挥手", "拥塞控制", "流量控制", "滑动窗口", "拥塞窗口", "慢启动", "拥塞避免", "快重传", "快恢复", "Reno", "Tahoe", "超时", "重传", "序号", "确认", "校验", "MSS", "RTT", "SACK", "SYN", "ACK", "FIN", "RST"]
        },
        {
            "id": "cn_application",
            "title": "应用层",
            "order": 6,
            "keywords": ["应用层", "DNS", "FTP", "SMTP", "POP3", "IMAP", "HTTP", "HTTPS", "WWW", "URL", "Web", "电子邮件", "Telnet", "SSH", "DHCP", "P2P", "CDN", "Cookie", "Session", "MIME", "文件传输", "远程登录", "域名", "递归查询", "迭代查询", "持久连接", "非持久"]
        },
    ],
    "操作系统": [
        {
            "id": "os_overview",
            "title": "操作系统概述",
            "order": 1,
            "keywords": ["操作系统", "OS", "批处理", "分时", "实时", "微内核", "宏内核", "系统调用", "中断", "异常", "管态", "目态", "内核态", "用户态", "特权指令", "非特权指令"]
        },
        {
            "id": "os_process",
            "title": "进程与线程",
            "order": 2,
            "keywords": ["进程", "线程", "PCB", "进程控制块", "状态", "就绪", "运行", "阻塞", "挂起", "切换", "上下文", "调度", "FCFS", "SJF", "SRTF", "轮转", "优先级", "多级队列", "信号量", "PV", "互斥", "同步", "管程", "死锁", "饥饿", "银行家", "安全序列"]
        },
        {
            "id": "os_memory",
            "title": "内存管理",
            "order": 3,
            "keywords": ["内存", "分区", "分页", "分段", "段页", "虚拟", "地址转换", "TLB", "页表", "快表", "页面置换", "OPT", "FIFO", "LRU", "CLOCK", "分配", "回收", "伙伴", "堆", "栈", "碎片", "共享", "保护"]
        },
        {
            "id": "os_file",
            "title": "文件管理",
            "order": 4,
            "keywords": ["文件", "目录", "FAT", "索引", "inode", "文件系统", "外存", "磁盘", "空闲空间", "位图", "链接", "FCB", "打开", "关闭", "读写", "保护", "权限"]
        },
        {
            "id": "os_io",
            "title": "输入输出(I/O)管理",
            "order": 5,
            "keywords": ["I/O", "IO", "设备", "控制器", "中断", "DMA", "通道", "缓冲", "SPOOLing", "假脱机", "虚拟设备", "独占", "共享", "设备分配", "设备调度", "磁盘调度", "先来先服务", "SCAN", "电梯", "C-SCAN"]
        },
    ],
}

def classify_kp(kp):
    """Classify a knowledge point into a chapter based on its title and content."""
    title = kp.get("title", "")
    content = kp.get("content", "")
    subject = kp.get("subject", "")
    
    # Combine title and content for matching, title gets higher weight
    text = title + " " + content
    text_lower = text.lower()
    
    chapters = CHAPTERS.get(subject, [])
    if not chapters:
        return {"chapter_id": "other", "chapter_title": subject, "chapter_order": 99}
    
    best_match = None
    best_score = 0
    
    for ch in chapters:
        score = 0
        for kw in ch["keywords"]:
            kw_lower = kw.lower()
            # Check in title (higher weight)
            title_matches = len(re.findall(re.escape(kw), title))
            score += title_matches * 3
            
            # Check in content (lower weight)
            content_matches = len(re.findall(re.escape(kw), content))
            score += content_matches
        
        if score > best_score:
            best_score = score
            best_match = ch
    
    # If no keywords matched, use page-based heuristics
    if best_score == 0:
        return {
            "chapter_id": "other",
            "chapter_title": "其他",
            "chapter_order": 99,
            "confidence": 0
        }
    
    return {
        "chapter_id": best_match["id"],
        "chapter_title": best_match["title"],
        "chapter_order": best_match["order"],
        "confidence": best_score
    }


def main():
    input_path = DATA / "knowledge_points.jsonl"
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return
    
    lines = open(input_path, 'r', encoding='utf-8').readlines()
    kps = []
    for line in lines:
        if line.strip():
            kps.append(json.loads(line))
    
    print(f"Loaded {len(kps)} knowledge points")
    
    # Classify each knowledge point
    stats = {}
    for kp in kps:
        result = classify_kp(kp)
        kp["chapter_id"] = result["chapter_id"]
        kp["chapter_title"] = result["chapter_title"]
        kp["chapter_order"] = result["chapter_order"]
        
        subject = kp["subject"]
        if subject not in stats:
            stats[subject] = {}
        ch_title = result["chapter_title"]
        if ch_title not in stats[subject]:
            stats[subject][ch_title] = 0
        stats[subject][ch_title] += 1
    
    # Save updated knowledge points
    output_path = DATA / "knowledge_points.jsonl"
    with open(output_path, 'w', encoding='utf-8') as f:
        for kp in kps:
            f.write(json.dumps(kp, ensure_ascii=False) + '\n')
    
    print(f"\nSaved {len(kps)} knowledge points with chapter info to {output_path}")
    
    # Print stats
    print("\n章节分布统计:")
    for subject, chapters in stats.items():
        print(f"\n{subject}:")
        # Sort by order
        sorted_chs = sorted(chapters.items(), key=lambda x: (
            [c["order"] for c in CHAPTERS.get(subject, []) if c["title"] == x[0]] or [99]
        ))
        for ch_title, count in sorted_chs:
            print(f"  {ch_title}: {count}")


if __name__ == "__main__":
    main()