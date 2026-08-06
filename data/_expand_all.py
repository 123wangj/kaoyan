"""扩充各科知识点的脚本。运行后会自动更新各 curriculum_*.py 文件。
新点采用 (chapter_id, new_points) 的形式注入。"""
import re
import os
import sys
import importlib

BASE = r'c:\Users\wang\Desktop\考研学习'
sys.path.insert(0, BASE)

# ============================================================
# 新增知识点字典：key=chapter_id, value=新点列表
# ============================================================

DS_NEW = {
    "ds_intro": [
        {"title": "数据结构的逻辑结构与物理结构", "content": "逻辑结构描述数据元素之间的逻辑关系（集合、线性、树、图），与存储无关；物理结构（存储结构）描述数据在计算机中的实际存储方式（顺序、链式、索引、散列）。同一逻辑结构可以采用不同的存储结构。", "score_points": ["逻辑结构四种分类", "存储结构四种", "逻辑结构独立于存储结构", "存储结构是逻辑结构的物理实现"], "difficulty": "基础", "tags": ["逻辑结构", "存储结构"]},
        {"title": "算法的复杂度分析", "content": "时间复杂度 T(n) 反映算法执行时间随问题规模 n 的增长趋势；空间复杂度 S(n) 反映算法所需存储空间。常见复杂度阶：O(1) < O(log n) < O(n) < O(n log n) < O(n²) < O(n³) < O(2ⁿ) < O(n!)。", "score_points": ["加法规则：取量级大的", "乘法规则：取乘积", "常见阶排序", "主项定理（Master 定理）"], "difficulty": "中等", "tags": ["时间复杂度", "空间复杂度"]},
        {"title": "递归与非递归算法", "content": "递归算法是直接或间接调用自身的算法，必须有递归终止条件。递归可简化代码，但可能产生大量重复计算（可用记忆化优化）。递归调用使用系统栈，每次调用保存返回地址和局部变量。", "score_points": ["递归三要素：终止条件、递归式、返回值", "递归转非递归", "尾递归可优化", "适用场景：分治、回溯、树图遍历"], "difficulty": "中等", "tags": ["递归", "栈", "分治"]},
    ],
    "ds_list": [
        {"title": "顺序表的插入与删除", "content": "顺序表插入元素最坏情况需要移动 n 个元素（插在表头），平均移动 n/2 个，时间复杂度 O(n)。删除同理。位序 i 处插入：检查 1≤i≤length+1，再从后向前移动。", "score_points": ["插入平均移动 n/2 个元素", "删除平均移动 (n-1)/2 个元素", "时间复杂度 O(n)", "尾插/尾删 O(1)"], "difficulty": "基础", "tags": ["顺序表", "插入", "删除"]},
        {"title": "链表的常见变形", "content": "双向链表每个节点有前驱和后继指针；循环单链表尾节点 next 指向头节点；循环双链表头节点 prev 指向尾节点。静态链表用数组下标代替指针，适合无指针语言。", "score_points": ["双向链表：prior+next", "循环单链表：可从任一节点遍历全表", "循环双链表判空条件", "静态链表：游标实现"], "difficulty": "中等", "tags": ["双向链表", "循环链表", "静态链表"]},
    ],
    "ds_stack_queue": [
        {"title": "栈的实现方式", "content": "顺序栈用数组实现，需预设容量；链栈用链表实现，无栈满问题（受内存限制）。共享栈可让两个顺序栈共享一维数组，提高空间利用率。", "score_points": ["顺序栈：top 指针", "链栈：头插法入栈", "共享栈：top0=-1, top1=MaxSize", "栈空栈满条件"], "difficulty": "基础", "tags": ["栈", "顺序栈", "链栈"]},
        {"title": "队列的实现方式", "content": "顺序队列使用数组+ front/rear 双指针；循环队列通过模运算实现逻辑上的环。链式队列用单链表实现。", "score_points": ["循环队列判空：front==rear", "循环队列判满：(rear+1)%MaxSize==front", "循环队列长度公式", "链式队列：队头删除队尾插入", "双端队列"], "difficulty": "基础", "tags": ["队列", "循环队列"]},
        {"title": "栈的应用：表达式求值", "content": "中缀表达式转后缀（逆波兰）使用栈：操作数直接输出，运算符与栈顶比较优先级再决定入栈或出栈。后缀表达式用栈求值：遇操作数入栈，遇运算符出栈两操作数运算后结果入栈。", "score_points": ["中缀转后缀：栈存运算符", "后缀求值：栈存操作数", "括号匹配", "递归→非递归", "逆波兰表达式"], "difficulty": "中等", "tags": ["栈", "表达式", "后缀"]},
        {"title": "队列的应用", "content": "队列先进先出（FIFO），典型应用：层次遍历二叉树、图的广度优先搜索（BFS）、操作系统进程调度、缓冲区管理、打印队列、消息队列。", "score_points": ["BFS 用队列", "树的层序遍历用队列", "进程就绪/等待队列", "缓冲区：生产者-消费者", "FCFS 调度使用就绪队列"], "difficulty": "基础", "tags": ["队列", "BFS"]},
        {"title": "数组与特殊矩阵", "content": "二维数组按行优先或列优先存储。对称矩阵可只存上（下）三角；三角矩阵只存非零部分；对角矩阵只存主对角线附近的元素；稀疏矩阵用三元组/十字链表压缩存储。", "score_points": ["行优先地址公式", "对称矩阵：n² 存 n(n+1)/2", "三角矩阵：n(n+1)/2", "稀疏矩阵：三元组", "十字链表：行链表+列链表"], "difficulty": "中等", "tags": ["数组", "矩阵压缩"]},
        {"title": "KMP 算法的 next 数组", "content": "KMP 算法通过 next 数组记录模式串的部分匹配信息，主串指针不回退，时间复杂度 O(m+n)。next[j] 表示 P[1..j] 中最长相等前后缀的长度。", "score_points": ["next[1]=0 规定", "next[j]=k 含义", "求 next 步骤", "nextval 数组优化", "时间复杂度 O(m+n)"], "difficulty": "较难", "tags": ["KMP", "next数组"]},
    ],
    "ds_tree": [
        {"title": "二叉树的特殊形态", "content": "满二叉树：高度 h，结点数 2^h-1；完全二叉树：除最后一层外每层满，最后一层从左到右连续；二叉排序树（BST）：左子树<根<右子树；平衡二叉树（AVL）：左右子树深度差不超过 1。", "score_points": ["满二叉树：2^h-1", "完全二叉树：深度 ⌊log₂n⌋+1", "二叉排序树：中序有序", "AVL 平衡因子", "堆：完全二叉树+父子大小关系"], "difficulty": "中等", "tags": ["二叉树", "满二叉树", "完全二叉树"]},
        {"title": "二叉树的存储结构", "content": "顺序存储用一维数组，适合完全二叉树（下标 i 的左孩子 2i、右孩子 2i+1、父亲 i/2）；链式存储用二叉链表（lchild+data+rchild）或三叉链表（+parent）。", "score_points": ["顺序存储：i 的左孩子 2i", "顺序存储：i 的右孩子 2i+1", "顺序存储：父亲 ⌊i/2⌋", "二叉链表：n+1 个空链域", "三叉链表：+parent"], "difficulty": "基础", "tags": ["存储结构", "二叉链表"]},
        {"title": "由遍历序列构造二叉树", "content": "已知前序（根左右）和中序（左根右）遍历序列，可唯一确定一棵二叉树。已知后序和中序也可。但前序+后序无法唯一确定（除非为满二叉树）。", "score_points": ["前序第一个是根", "中序定位根后分左右", "递归构造左右子树", "时间复杂度 O(n)", "前+后不能唯一确定"], "difficulty": "中等", "tags": ["遍历", "构造"]},
        {"title": "树、森林与二叉树的转换", "content": "树转二叉树：长子作为左子树，兄弟作为右子树。森林转二叉树：森林中每棵树转为二叉树，前一棵树的根作为后一棵树的右子树。二叉树转树/森林：逆转。", "score_points": ["树→二叉树：左孩子右兄弟", "二叉树→树：右子树是兄弟", "森林→二叉树：合并右子树链", "树的遍历：先根、后根"], "difficulty": "中等", "tags": ["树", "森林", "转换"]},
        {"title": "并查集", "content": "并查集处理集合合并与查询问题。使用树（数组）表示集合，find 找根、union 合并。优化：路径压缩 + 按秩合并，使单次操作接近 O(1)（实际 O(α(n))）。", "score_points": ["Find(x)：找根", "Union(a,b)：合并", "路径压缩", "按秩合并", "应用：Kruskal、连通性"], "difficulty": "中等", "tags": ["并查集", "路径压缩"]},
        {"title": "B-树与 B+树", "content": "B-树是平衡的多路查找树，每个节点最多 m 个关键字、m+1 个孩子，叶节点在同一层。B+树是 B-树的变体，所有关键字都在叶节点出现，叶节点链表相连，适合范围查询。", "score_points": ["B-树阶 m 关键字数", "B+树叶子链表", "B+树非叶是索引", "磁盘 I/O = 树高", "B+树范围查询优"], "difficulty": "较难", "tags": ["B树", "B+树", "磁盘"]},
    ],
    "ds_graph": [
        {"title": "图的基本术语", "content": "无向图：边无方向；完全图：无向图 n(n-1)/2 边，有向图 n(n-1) 边。子图：顶点和边都是原图子集。度：顶点关联的边数（无向图）；入度/出度（有向图）。连通图：任意两顶点连通。", "score_points": ["无向完全图边数 n(n-1)/2", "有向完全图边数 n(n-1)", "无向图度数之和 = 2|E|", "有向图入度之和=出度之和", "连通图：n 顶点至少 n-1 边"], "difficulty": "基础", "tags": ["图", "术语"]},
        {"title": "图的深度优先遍历（DFS）", "content": "DFS 模仿树的先序遍历：访问顶点 v → 递归访问 v 的所有未访问邻接点。需 visited[] 数组避免循环。邻接表时间 O(n+e)，邻接矩阵 O(n²)。", "score_points": ["递归实现：栈", "时间复杂度：邻接表 O(n+e)", "空间复杂度 O(n)", "非连通图：每个连通分量都 DFS"], "difficulty": "基础", "tags": ["DFS", "深度优先"]},
        {"title": "Prim 算法求最小生成树", "content": "Prim 算法从任一顶点出发，每次选择连接已选顶点集与未选顶点集的最短边加入生成树，直至所有顶点加入。适合稠密图，时间复杂度 O(n²)，用邻接矩阵实现。", "score_points": ["初始：任选一顶点加入 U", "每步：选 U 到 V-U 的最短边", "时间复杂度 O(n²)，适合稠密图", "可优化为 O(nlogn)", "适用于连通无向图"], "difficulty": "中等", "tags": ["Prim", "MST"]},
        {"title": "Kruskal 算法求最小生成树", "content": "Kruskal 算法按边权从小到大依次选择，如果边的两端不连通（用并查集判断）则加入生成树，直至选了 n-1 条边。适合稀疏图，时间复杂度 O(e log e)。", "score_points": ["按边权升序排序", "用并查集判连通", "跳过形成环的边", "时间复杂度 O(eloge)", "适合稀疏图"], "difficulty": "中等", "tags": ["Kruskal", "并查集", "MST"]},
        {"title": "Dijkstra 最短路径算法", "content": "Dijkstra 求单源最短路径：每次从未确定顶点中选距离最小的，加入已确定集合，更新其邻居距离。要求边权非负。时间复杂度 O(n²) 或 O((n+e)log n)（堆优化）。", "score_points": ["初始：源点距离 0，其他 ∞", "每步：选 min 距离点", "更新邻居距离", "不能处理负权边", "堆优化 O((n+e)logn)"], "difficulty": "中等", "tags": ["Dijkstra", "最短路径"]},
        {"title": "Floyd-Warshall 算法", "content": "Floyd 求所有顶点对之间最短路径。状态转移：dist[i][j]=min(dist[i][j], dist[i][k]+dist[k][j])，k 依次为 0..n-1。时间复杂度 O(n³)，可处理负权边（但不能有负权环）。", "score_points": ["三重循环：k-i-j", "状态转移方程", "可处理负权边（无负环）", "时间复杂度 O(n³)", "可检测负权环"], "difficulty": "中等", "tags": ["Floyd", "全源最短路径"]},
        {"title": "拓扑排序", "content": "拓扑排序将 DAG（有向无环图）的顶点排成线性序列，使得每条有向边 u→v，u 在 v 之前。算法：选入度为 0 的顶点输出，删除其出边，重复。时间复杂度 O(n+e)。", "score_points": ["AOV 网：顶点表示活动", "选入度 0 顶点输出", "栈/队列存储入度 0 顶点", "DAG 一定有拓扑序列", "判环：最后输出 < n"], "difficulty": "中等", "tags": ["拓扑排序", "DAG", "AOV"]},
        {"title": "关键路径", "content": "AOE 网（边表示活动）求关键路径：事件最早发生时间 ve、事件最迟发生时间 vl、活动最早开始时间 e、活动最迟开始时间 l，l==e 的活动为关键活动，关键路径是最长路径。", "score_points": ["ve：源点到该点最长路", "vl：终点 ve - 最长反向路", "e：起点 ve", "l：终点 vl - 边权", "关键活动：e==l"], "difficulty": "较难", "tags": ["关键路径", "AOE"]},
    ],
    "ds_search": [
        {"title": "顺序查找", "content": "顺序查找（线性查找）：从表的一端开始，逐个比较关键字与给定值，时间复杂度 O(n)。可设置哨兵避免每次判断越界。", "score_points": ["平均查找长度 (n+1)/2", "时间复杂度 O(n)", "对数据无要求", "哨兵：表尾放待查值"], "difficulty": "基础", "tags": ["顺序查找", "线性查找"]},
        {"title": "分块查找", "content": "分块查找（索引顺序查找）：将表分成若干块，块内无序、块间有序。建立索引表（每块最大关键字+起始地址），先在索引表二分/顺序找块，再在块内顺序查找。", "score_points": ["块内无序，块间有序", "索引表保存每块最大关键字", "先查索引再查块", "ASL 近似公式"], "difficulty": "中等", "tags": ["分块查找", "索引查找"]},
        {"title": "二叉排序树（BST）", "content": "BST：左子树所有节点 < 根 < 右子树所有节点。中序遍历得有序序列。查找、插入、删除时间平均 O(log n)，最坏 O(n)（退化为链表）。", "score_points": ["定义：左 < 根 < 右", "中序遍历有序", "查找：与根比大小走左/右", "删除：3 种情况", "ASL 取决于树高"], "difficulty": "中等", "tags": ["BST", "二叉排序树"]},
        {"title": "平衡二叉树（AVL）", "content": "AVL 树：任意节点的左右子树高度差（平衡因子）绝对值 ≤ 1。插入破坏平衡时通过 4 种旋转调整：LL、RR、LR、RL。查找复杂度 O(log n)。", "score_points": ["平衡因子 ∈ {-1,0,1}", "LL：右单旋", "RR：左单旋", "LR：左右双旋", "RL：右左双旋", "ASL = log₂n 量级"], "difficulty": "较难", "tags": ["AVL", "平衡二叉树", "旋转"]},
        {"title": "红黑树", "content": "红黑树是自平衡二叉查找树，每个节点有红/黑标记。满足 5 条性质：从根到叶路径黑节点数相同；红色节点不能连续；根是黑色。插入/删除通过变色和旋转保持平衡，O(log n)。", "score_points": ["5 条性质", "最长路径 ≤ 2× 最短路径", "插入最多 2 次旋转", "删除最多 3 次旋转", "C++ STL map/set 内部用红黑树"], "difficulty": "较难", "tags": ["红黑树", "自平衡"]},
        {"title": "散列函数的构造", "content": "常用散列函数：直接定址法（线性）、除留余数法 H(k)=k%p（p 选素数）、数字分析法、平方取中法、折叠法。", "score_points": ["除留余数：p 选最大素数", "直接定址：H(k)=a*k+b", "数字分析：取分布均匀位", "平方取中：取平方中间位"], "difficulty": "基础", "tags": ["散列函数", "哈希函数"]},
        {"title": "处理冲突的方法", "content": "开放定址法：线性探测（逐个往后）、平方探测（±1,±4,..）、双散列、伪随机探测。拉链法：同义词用链表串起来。", "score_points": ["线性探测：易聚集", "平方探测：减轻聚集", "拉链法：适合插入删除", "再散列：装填因子过大", "装填因子 α=n/m"], "difficulty": "中等", "tags": ["哈希冲突", "拉链法", "探测"]},
    ],
    "ds_sort": [
        {"title": "插入排序", "content": "直接插入排序：将待排序元素插入到已排序序列的合适位置。最好情况 O(n)（已序），最坏 O(n²)。折半插入排序减少了比较次数，移动次数仍 O(n²)。希尔排序：分组插入，缩小增量。", "score_points": ["直接插入：稳定 O(n²)", "折半插入：减少比较，仍 O(n²)", "希尔：缩小增量分组", "希尔不稳定", "希尔最坏 O(n^1.3)"], "difficulty": "基础", "tags": ["插入排序", "希尔排序"]},
        {"title": "快速排序", "content": "快速排序：选 pivot（基准），将序列分为 < pivot 和 > pivot 两部分，递归排序。平均 O(n log n)，最坏 O(n²)（已序）。优化：三数取中、随机化、非递归。", "score_points": ["分治思想", "递归实现", "平均 O(nlogn)，最坏 O(n²)", "不稳定", "空间 O(logn)", "三数取中法避免最坏"], "difficulty": "中等", "tags": ["快速排序", "分治"]},
        {"title": "堆排序", "content": "堆排序：先将数组调整为最大堆，然后反复取堆顶（最大元素）放到数组末尾，再调整堆。时间 O(n log n)，空间 O(1)，不稳定。", "score_points": ["建堆 O(n)", "排序 O(nlogn)", "总时间 O(nlogn)", "空间 O(1)", "不稳定", "适合大数据量"], "difficulty": "中等", "tags": ["堆排序", "堆"]},
        {"title": "归并排序", "content": "归并排序：分治，将序列分成两半分别排序，再合并两个有序序列。O(n log n)，稳定。需 O(n) 辅助空间（可用链表优化空间）。", "score_points": ["分治：分-治-合", "时间 O(nlogn)", "空间 O(n)", "稳定", "适合链表排序", "外部排序常用"], "difficulty": "中等", "tags": ["归并排序", "分治"]},
        {"title": "基数排序", "content": "基数排序：按关键字各位\"分配+收集\"，从低位到高位（或相反），多次稳定排序。O(d(n+r))，d 为位数，r 为基数。稳定，适合整数/字符串。", "score_points": ["分配+收集", "从低位到高位", "稳定", "时间 O(d(n+r))", "空间 O(r)"], "difficulty": "中等", "tags": ["基数排序"]},
        {"title": "排序算法比较", "content": "稳定的排序：直接插入、冒泡、归并、基数。不稳定：希尔、堆、快速、简单选择。内排序：所有操作在内存；外排序：数据太大借助磁盘（多路归并）。", "score_points": ["稳定的：插入、冒泡、归并、基数", "不稳定的：希尔、堆、快排、选择", "内排序 vs 外排序", "时间复杂度下限 O(nlogn)"], "difficulty": "中等", "tags": ["排序比较", "稳定性"]},
    ],
}

CO_NEW = {
    "co_overview": [
        {"title": "计算机的发展历程", "content": "电子计算机经历了电子管、晶体管、中小规模集成电路、大规模/超大规模集成电路四代。未来的量子计算机、光计算机等是新的发展方向。", "score_points": ["第一代：电子管(1946-1957)", "第二代：晶体管(1958-1964)", "第三代：中小规模 IC(1965-1971)", "第四代：大/超大规模 IC(1972-)", "微型计算机属于第四代"], "difficulty": "基础", "tags": ["发展", "计算机历史"]},
        {"title": "计算机硬件与软件关系", "content": "硬件是物理实体，软件是程序和数据。系统软件管理硬件，应用软件解决具体问题。软硬件在逻辑功能上等价（某些功能可由硬件或软件实现）。", "score_points": ["系统软件：OS、编译程序、DBMS", "应用软件：解决实际问题", "软硬件等价性", "软件硬化、硬件软化"], "difficulty": "基础", "tags": ["硬件", "软件"]},
        {"title": "CPU 性能公式", "content": "CPU 执行时间 = 指令数 × CPI × 时钟周期。CPI（每条指令时钟周期数）是衡量 CPU 性能的重要指标。", "score_points": ["T = IC × CPI × T_clock", "MIPS = 主频 / (CPI × 10^6)", "MFLOPS 衡量浮点性能", "Amdahl 定律：系统加速比"], "difficulty": "中等", "tags": ["CPU", "性能"]},
    ],
    "co_data": [
        {"title": "IEEE 754 浮点数标准", "content": "IEEE 754 单精度 32 位：1 位符号 + 8 位阶码（含偏置 127）+ 23 位尾数；双精度 64 位：1 + 11(含偏置 1023) + 52。规格化数：1.M 形式。", "score_points": ["单精度：1+8+23=32", "双精度：1+11+52=64", "偏置：单 127，双 1023", "规格化：1.M，阶码非全 0 非全 1", "非规格化：阶码全 0，尾数 0.M"], "difficulty": "中等", "tags": ["IEEE754", "浮点数"]},
        {"title": "数据的存储与排列", "content": "大端模式：高位字节在低地址（网络字节序）。小端模式：低位字节在低地址（x86）。边界对齐：数据按字/半字/双字边界存放，提高访问效率。", "score_points": ["大端：高位在低地址", "小端：低位在低地址", "对齐访问：地址为长度整数倍", "未对齐：可能多次访存"], "difficulty": "基础", "tags": ["大小端", "对齐"]},
        {"title": "定点数运算", "content": "补码加减法：[A+B]补=[A]补+[B]补，[A-B]补=[A]补+[-B]补。溢出判别：双符号位法（变形补码）或进位法（单符号位）。乘法：原码一位乘、布斯乘法（补码）。", "score_points": ["补码加减：符号位参与运算", "溢出：两正相加负或两负相加正", "双符号位：01 正溢/10 负溢", "原码一位乘：移位累加", "Booth 算法：补码乘法"], "difficulty": "较难", "tags": ["补码", "溢出", "乘法"]},
        {"title": "浮点数加减运算", "content": "步骤：对阶（小阶向大阶对齐）→ 尾数加减 → 规格化（结果需满足 1.M 形式）→ 舍入（0 舍 1 入/恒置 1）→ 判溢出（阶码上溢）。", "score_points": ["对阶：小→大，尾数右移", "尾数加减：双符号位补码", "规格化：左规/右规", "舍入：保护位处理", "判溢出：阶码超出范围"], "difficulty": "较难", "tags": ["浮点运算", "对阶", "规格化"]},
    ],
    "co_memory": [
        {"title": "主存储器的基本结构", "content": "主存由存储体、地址寄存器(MAR)、数据寄存器(MDR)组成。地址译码器选中所访问单元。存取时间 Ta、存取周期 Tm（通常 Ta<Tm）。", "score_points": ["MAR：地址寄存器", "MDR：数据寄存器", "存储矩阵：大量存储单元", "地址译码：选通一行", "Ta：启动到完成读写", "Tm：两次独立存取最小间隔"], "difficulty": "基础", "tags": ["主存", "MAR", "MDR"]},
        {"title": "SRAM 与 DRAM", "content": "SRAM（静态 RAM）：用触发器，6 管/单元，无需刷新，速度快，用作 Cache。DRAM（动态 RAM）：用电容+晶体管，1 管/单元，需定期刷新，密度高，用作主存。", "score_points": ["SRAM：6 管/单元，快，贵", "DRAM：1 管/单元，慢，密", "DRAM 需刷新（约 2ms）", "刷新方式：集中/分散/异步", "DDR：双倍数据率 SDRAM"], "difficulty": "中等", "tags": ["SRAM", "DRAM", "刷新"]},
        {"title": "Cache 替换算法", "content": "Cache 满时选择替换哪一块。算法：随机算法、FIFO（先进先出）、LRU（最近最少使用，最常用）、LFU（最不经常使用）。LRU 实现：计数器法/栈。", "score_points": ["FIFO：先进先出", "LRU：最近最久未使用最优", "LFU：访问次数最少", "计数器法", "栈实现", "OPT 理论最优但不可实现"], "difficulty": "中等", "tags": ["替换算法", "LRU", "FIFO"]},
        {"title": "Cache 写策略", "content": "写直达（Write Through）：同时写 Cache 和主存。写回（Write Back）：只写 Cache，块被替换时写回主存。写分配（Write Allocate）：写未命中时调入 Cache；非写分配则直接写主存。", "score_points": ["写直达：一致性好，速度慢", "写回：速度快，块有脏位", "写分配：写未命中调入", "非写分配：直接写主存"], "difficulty": "中等", "tags": ["写策略", "一致性"]},
        {"title": "页式虚拟存储器", "content": "虚拟存储器由主存+辅存构成，地址空间逻辑上远大于主存。页式管理：虚页→实页（页框），由页表（页号→块号）映射。缺页时从辅存调页。", "score_points": ["页表：虚页号→实页号", "页表基址寄存器 PTBR", "TLB 快表：页表 Cache", "缺页：从辅存调入主存", "页面大小通常 4KB"], "difficulty": "较难", "tags": ["虚拟存储", "页表", "缺页"]},
    ],
    "co_instruction": [
        {"title": "指令的寻址方式", "content": "指令寻址：顺序寻址（PC+1）和跳跃寻址（转移类）。操作数寻址：立即寻址（地址码=操作数）、直接寻址（地址码=有效地址）、间接寻址（地址码指向 EA 单元）、寄存器寻址、寄存器间接、基址/变址/相对寻址、堆栈寻址。", "score_points": ["立即数：地址字段就是操作数", "直接：地址字段=EA", "间接：地址字段指向 EA", "寄存器：地址字段是寄存器号", "基址：EA=基址寄存器+形式地址", "变址：EA=变址寄存器+形式地址", "相对：EA=PC+形式地址"], "difficulty": "中等", "tags": ["寻址方式", "指令"]},
        {"title": "指令格式设计", "content": "指令由操作码（OP）+ 地址码组成。操作码长度决定指令种类数（2ⁿ种），地址码个数（零/一/二/三/四地址）。零地址用于堆栈。", "score_points": ["操作码：n 位 → 2ⁿ 条指令", "零地址：堆栈操作", "一地址：单操作数/隐含另一操作数（ACC）", "二地址：常用", "三地址：功能强"], "difficulty": "中等", "tags": ["指令格式", "操作码"]},
    ],
    "co_cpu": [
        {"title": "CPU 内部寄存器", "content": "CPU 内部主要寄存器：PC（程序计数器，存下条指令地址）、IR（指令寄存器，存当前指令）、ACC（累加器）、通用寄存器组（GPRs）、PSW（程序状态字：标志位）、MAR/MDR（与主存接口）、SP（堆栈指针）。", "score_points": ["PC：下一条指令地址", "IR：当前指令", "PSW：标志位（ZF、CF、OF、SF）", "SP：栈顶指针", "GPRs：通用寄存器组"], "difficulty": "基础", "tags": ["寄存器", "CPU"]},
        {"title": "微程序控制器", "content": "微程序控制器用微指令序列实现指令功能。微指令由操作控制字段+顺序控制字段组成。微周期=读微指令时间+执行微操作时间。微程序存于控制存储器（ROM）。", "score_points": ["微指令：基本微操作命令", "微程序：一组微指令", "控制存储器 CM 存微程序", "微地址：微指令在 CM 中的地址", "水平/垂直微指令"], "difficulty": "较难", "tags": ["微程序", "控制器"]},
        {"title": "流水线冒险与处理", "content": "流水线冒险：结构冒险（资源冲突）、数据冒险（RAW/WAR/WAW）、控制冒险（转移）。处理：停顿（bubble）、转发（forwarding/bypassing）、分支预测、延迟槽。", "score_points": ["结构冒险：硬件资源不足", "数据冒险 RAW：写后读", "数据转发：ALU→ALU input", "控制冒险：分支延迟", "动态分支预测：BTB/2-bit", "延迟槽：编译器填充"], "difficulty": "较难", "tags": ["流水线", "冒险"]},
        {"title": "流水线性能指标", "content": "流水线吞吐率 TP = n/Tk（n 任务数，Tk 完成时间）。加速比 S = T0/Tk。效率 E = 加速比/段数。", "score_points": ["TP = n / (k+n-1)Δt 近似", "S = nkΔt / (k+n-1)Δt", "E = S/k", "理想：TP=1/Δt, S=k, E=1"], "difficulty": "中等", "tags": ["流水线性能", "吞吐率"]},
    ],
    "co_bus": [
        {"title": "总线标准与性能指标", "content": "总线性能指标：总线宽度（数据线位数）、总线带宽（MB/s = 宽度×频率/8）、时钟频率、总线复用。常见总线：PCI、PCIe、USB、SATA、I²C。", "score_points": ["总线带宽 = 位宽 × 频率 / 8", "PCI 32 位/33MHz ≈ 132MB/s", "PCIe x1 单向 250MB/s", "USB 2.0 480Mbps, USB 3.0 5Gbps"], "difficulty": "基础", "tags": ["总线", "带宽"]},
        {"title": "总线定时与传输", "content": "总线定时方式：同步定时（统一时钟）、异步定时（握手信号）、半同步定时。突发传输：连续多个数据块传输。", "score_points": ["同步：统一时钟", "异步：握手，应答", "半同步：同步+等待信号", "突发：连续传输"], "difficulty": "中等", "tags": ["总线定时", "传输"]},
    ],
    "co_io": [
        {"title": "I/O 接口与编址", "content": "I/O 接口连接 CPU 和外设。I/O 端口编址：独立编址（IN/OUT 指令，端口空间独立）、统一编址（内存映射 I/O）。接口功能：数据缓冲、命令、状态、设备选择。", "score_points": ["独立编址：专用 I/O 指令", "统一编址：与内存共享地址空间", "接口寄存器：数据/控制/状态", "DMA 控制器：8237", "中断控制器：8259A"], "difficulty": "中等", "tags": ["I/O", "接口"]},
        {"title": "中断处理过程", "content": "中断处理：中断请求→中断判优→中断响应（保存 PC、PSW）→中断服务（识别中断源）→中断处理（执行 ISR）→中断返回（恢复现场）。", "score_points": ["中断源：内部/外部", "中断判优：硬件/软件", "保存现场：PC、PSW 压栈", "中断向量：中断服务程序入口", "中断嵌套", "中断屏蔽"], "difficulty": "中等", "tags": ["中断", "处理"]},
    ],
}

OS_NEW = {
    "os_intro": [
        {"title": "操作系统的特征", "content": "OS 四大特征：并发（多个事件在同一时间间隔内交替执行）、共享（资源可供多个并发进程使用）、虚拟（将一个物理实体映射为多个逻辑实体）、异步（进程以不可预知速度推进）。", "score_points": ["并发：宏观同时，微观交替", "共享：互斥/同时访问", "虚拟：时分复用、空分复用", "异步：走走停停", "并发和共享是 OS 最基本特征"], "difficulty": "基础", "tags": ["OS特征", "并发", "共享"]},
        {"title": "操作系统的内核", "content": "内核是 OS 核心部分，包括：时钟管理（提供时间基准）、中断机制（系统调用基础）、原语（原子操作）、进程管理、存储器管理、设备管理。", "score_points": ["内核 = 时钟 + 中断 + 原语 + 管理模块", "内核态 vs 用户态", "系统调用：用户态→内核态", "原语：原子操作，不可中断"], "difficulty": "中等", "tags": ["内核", "系统调用"]},
    ],
    "os_process": [
        {"title": "进程控制块（PCB）", "content": "PCB 是进程存在的唯一标识，包含：进程描述信息（PID、UID）、进程控制信息（状态、优先级）、资源信息（打开文件、占用内存）、CPU 现场（寄存器值、PC）。", "score_points": ["PID：进程标识", "进程状态：运行/就绪/阻塞", "程序计数器 PC", "寄存器上下文", "打开文件表指针", "PCB 存于内核区"], "difficulty": "基础", "tags": ["PCB", "进程控制"]},
        {"title": "进程控制原语", "content": "进程控制原语（原子操作）：创建（fork/exec）、终止（exit）、阻塞（wait）、唤醒（signal）、挂起、激活。", "score_points": ["创建原语：申请 PCB，填信息", "终止：回收资源，撤销 PCB", "阻塞：运行→阻塞", "唤醒：阻塞→就绪", "挂起/激活"], "difficulty": "中等", "tags": ["原语", "进程控制"]},
        {"title": "线程与协程", "content": "线程是 CPU 调度的基本单位，是轻量级进程。同一进程的线程共享地址空间和资源。协程是用户态线程，由程序自身控制调度，开销极小。", "score_points": ["线程 = 轻型进程", "共享：代码段、堆、全局变量", "私有：TCB、栈、寄存器", "用户级 vs 内核级线程", "协程：用户态切换", "Go 协程 goroutine"], "difficulty": "中等", "tags": ["线程", "协程"]},
        {"title": "进程间通信（IPC）", "content": "IPC 方式：管道（Pipe，半双工，父子进程）、命名管道（FIFO，无亲缘关系）、消息队列（消息链表）、共享内存（最快，需同步）、信号量、Socket（不同主机）。", "score_points": ["管道：半双工，字节流", "命名管道：文件系统路径", "消息队列：消息链表", "共享内存：最快，需同步", "信号量：PV 操作同步", "Socket：TCP/UDP"], "difficulty": "中等", "tags": ["IPC", "通信"]},
        {"title": "处理机调度", "content": "调度层次：高级调度（作业调度）、中级调度（内存调度，置换）、低级调度（进程调度）。调度算法：FCFS、SJF（短作业优先）、优先级、时间片轮转、多级反馈队列。", "score_points": ["高级：作业→内存", "中级：内存↔外存", "低级：内存→CPU", "FCFS：先来先服务", "SJF：最短优先", "时间片轮转：公平", "多级反馈队列：综合"], "difficulty": "中等", "tags": ["调度", "算法"]},
    ],
    "os_sync": [
        {"title": "临界区与同步原则", "content": "临界资源：一次仅允许一个进程使用的资源。临界区：访问临界资源的代码段。同步原则：空闲让进、忙则等待、有限等待、让权等待。", "score_points": ["临界资源：互斥访问", "临界区：访问代码", "空闲让进：资源空闲允许进入", "忙则等待：已有进程等待", "有限等待：避免饥饿", "让权等待：释放 CPU"], "difficulty": "基础", "tags": ["临界区", "同步"]},
        {"title": "信号量机制", "content": "信号量（Semaphore）：整型变量 + P/V 操作。P(S) 申请资源（S>=0 时 S--，否则阻塞）；V(S) 释放资源（S++，唤醒等待者）。可实现互斥（初值 1）和同步（初值 0）。", "score_points": ["P 操作：wait，s--", "V 操作：signal，s++", "互斥：初值 1", "同步：初值 0（消费者）", "P/V 必须成对出现", "管程：高级同步原语"], "difficulty": "中等", "tags": ["信号量", "PV", "同步"]},
        {"title": "经典同步问题", "content": "生产者-消费者：缓冲池满/空时阻塞。读者-写者：读可并发，写独占。哲学家就餐：5 人 5 筷子，慎防死锁。可用信号量或管程解决。", "score_points": ["生产者-消费者：3 个信号量", "读者优先：readcount 计数", "写者优先：复杂", "哲学家：拿左再拿右（不对称）", "死锁预防：资源排序"], "difficulty": "较难", "tags": ["生产者消费者", "读者写者", "哲学家"]},
        {"title": "管程", "content": "管程（Monitor）：高级同步原语，封装共享变量及操作。同一时刻只有一个进程在管程内活动（互斥），通过条件变量 wait/signal 实现同步。", "score_points": ["管程 = 数据 + 操作 + 同步", "互斥进入", "条件变量：wait/signal", "Hoare 管程：signal 立即切换", "Mesa 管程：signal 后继续", "Java synchronized"], "difficulty": "较难", "tags": ["管程", "monitor"]},
        {"title": "死锁", "content": "死锁四条件：互斥、占有并等待、不可剥夺、循环等待。处理策略：预防（破坏任一条件）、避免（银行家算法）、检测+恢复、忽略（鸵鸟算法）。", "score_points": ["四必要条件", "预防：一次性分配/剥夺", "银行家算法：安全序列", "检测：资源分配图", "恢复：撤销进程/剥夺资源", "鸵鸟：装作不知道"], "difficulty": "较难", "tags": ["死锁", "银行家"]},
    ],
    "os_memory": [
        {"title": "连续分配管理", "content": "连续分配：单一连续（单用户）、固定分区（多用户但内部碎片）、动态分区（最佳/首次/最差适配，外部碎片）。紧凑可解决外部碎片。", "score_points": ["固定分区：内部碎片", "动态分区：外部碎片", "首次适配：简单", "最佳适配：碎片小", "最差适配：大剩余", "紧凑：移动程序"], "difficulty": "基础", "tags": ["连续分配", "分区"]},
        {"title": "分页存储管理", "content": "分页：逻辑地址 = 页号P + 页内偏移W，物理地址 = 块号 + 偏移。页表保存页号→块号。页大小通常 4KB，地址空间分为等大小页。", "score_points": ["页号 P = 逻辑地址 / 页大小", "页内偏移 W = 逻辑地址 % 页大小", "页表：P → 块号", "页表寄存器 PTR", "TLB：快表"], "difficulty": "中等", "tags": ["分页", "页表"]},
        {"title": "分段存储管理", "content": "分段：按逻辑模块（主程序段、数据段、栈段）划分，每段从 0 开始编址。地址 = 段号 + 段内偏移。段表：段号→基址+段长。便于共享和保护。", "score_points": ["段：逻辑单位", "地址 = 段号 + 段内偏移", "段表：段号→(基址, 段长)", "段内越界保护", "段页式：段内再分页", "便于代码共享"], "difficulty": "中等", "tags": ["分段", "段表"]},
        {"title": "虚拟存储与页面置换", "content": "虚拟存储器：仅将活跃部分装入内存，按需调页（请求分页）。页面置换算法：OPT（理论最优）、FIFO（先进先出，可能 Belady 异常）、LRU（最近最久未使用）、CLOCK（改进型）。", "score_points": ["OPT：未来最久不使用", "FIFO：先进先出", "LRU：最近最久未用", "CLOCK：访问位，环形", "抖动：频繁换页", "Belady 异常：FIFO 才有"], "difficulty": "较难", "tags": ["虚拟存储", "置换"]},
    ],
    "os_file": [
        {"title": "文件的逻辑结构", "content": "逻辑结构：有结构（记录式，如数据库文件）和无结构（流式，如文本）。组织方式：顺序文件、索引文件、索引顺序文件。直接文件和哈希文件支持快速访问。", "score_points": ["有结构 vs 无结构", "顺序文件：顺序存取", "索引文件：变长记录+索引", "索引顺序：分组+总索引", "直接文件：哈希"], "difficulty": "基础", "tags": ["文件结构", "逻辑结构"]},
        {"title": "文件的物理结构", "content": "物理结构：连续分配（顺序读写快，外部碎片）、链接分配（隐式/显式，无碎片但随机访问慢）、索引分配（索引块，支持随机访问，可多级/混合索引）。", "score_points": ["连续：顺序访问快", "链接：FAT 显式链表", "索引：单级/多级/混合", "UNIX 混合索引：13 块地址", "FCB：文件控制块"], "difficulty": "中等", "tags": ["物理结构", "分配"]},
        {"title": "目录管理", "content": "目录结构：一级（限制多）、二级（用户分目录）、多级（树形）、无环图（共享）。FCB 存放文件元数据。文件操作：创建、删除、打开、关闭、读、写。", "score_points": ["FCB：文件名/属性/位置", "一级：仅根目录", "二级：用户目录", "树形：路径唯一", "无环图：共享文件"], "difficulty": "基础", "tags": ["目录", "FCB"]},
        {"title": "磁盘调度算法", "content": "磁盘调度目标：减少寻道时间。算法：FCFS（先来先服务）、SSTF（最短寻道优先）、SCAN（电梯算法，来回扫描）、C-SCAN（单向扫描）、LOOK/C-LOOK（不走到端点）。", "score_points": ["FCFS：公平但慢", "SSTF：可能饥饿", "SCAN：来回扫描", "C-SCAN：单向", "LOOK：不到端点", "调度单位：磁道或柱面"], "difficulty": "中等", "tags": ["磁盘调度", "SCAN"]},
    ],
    "os_io": [
        {"title": "I/O 控制方式", "content": "四种 I/O 控制方式：程序查询（CPU 忙等）、中断方式（I/O 完成后中断 CPU）、DMA（直接存储器访问，块传送无需 CPU）、通道（专门 I/O 处理器，复杂）。", "score_points": ["程序查询：简单，CPU 浪费", "中断：每次一字，效率提高", "DMA：块传送，CPU 介入少", "通道：专门处理器"], "difficulty": "中等", "tags": ["I/O控制", "DMA"]},
        {"title": "缓冲管理", "content": "缓冲区：缓解 CPU 与 I/O 速度差异。类型：单缓冲、双缓冲、循环缓冲、缓冲池。SPOOLing（Simultaneous Peripheral Operations On-Line）技术用磁盘模拟独占设备。", "score_points": ["单缓冲：处理一块时读下一块", "双缓冲：并行处理", "循环缓冲：多块循环", "缓冲池：通用管理", "SPOOLing：设备共享"], "difficulty": "中等", "tags": ["缓冲", "SPOOLing"]},
    ],
}

CN_NEW = {
    "cn_arch": [
        {"title": "TCP/IP 四层模型", "content": "TCP/IP 四层：网络接口层（链路层+物理）、网际层（IP）、传输层（TCP/UDP）、应用层（HTTP/FTP/DNS/SMTP）。实际互联网使用。", "score_points": ["网络接口层", "网际层 IP", "传输层 TCP/UDP", "应用层：所有应用协议", "OSI 与 TCP/IP 对应关系", "TCP/IP 是事实标准"], "difficulty": "基础", "tags": ["TCP/IP", "四层"]},
        {"title": "网络性能指标", "content": "性能指标：带宽（理论最高速率，Hz/bps）、时延（发送+传播+处理+排队）、吞吐量（实际平均速率）、时延带宽积（=传播时延×带宽）、往返时间 RTT、利用率。", "score_points": ["时延 = 发送+传播+处理+排队", "传播时延 = 距离/传播速度", "发送时延 = 数据长度/带宽", "时延带宽积 = 传播时延×带宽", "RTT：往返时间"], "difficulty": "中等", "tags": ["性能", "时延"]},
    ],
    "cn_physical": [
        {"title": "编码与调制", "content": "数字数据编码为数字信号：NRZ（不归零）、曼彻斯特（前 1 后 0 = 1，前 0 后 1 = 0）、差分曼彻斯特。模拟数据编码为模拟信号：AM/FM/PM。数字数据调制为模拟信号：ASK/FSK/PSK。", "score_points": ["曼彻斯特：位中跳变", "差分曼彻斯特：位初跳变", "NRZ：简单但无同步", "ASK：调幅", "FSK：调频", "PSK：调相"], "difficulty": "中等", "tags": ["编码", "调制"]},
        {"title": "数据交换方式", "content": "数据交换三种方式：电路交换（建立连接→通信→释放，时延小但线路利用率低）、报文交换（存储转发，延迟大）、分组交换（包为单位，转发延迟小，效率高，是主流）。", "score_points": ["电路：独占信道", "报文：整段存储转发", "分组：分段存储转发", "分组时延小、效率高", "虚电路：逻辑连接+分组交换", "数据报：无连接分组交换"], "difficulty": "中等", "tags": ["交换方式", "分组"]},
    ],
    "cn_datalink": [
        {"title": "流量控制与可靠传输", "content": "流量控制：发送方别发太快。停止-等待协议：每发一帧等确认。滑动窗口协议：连续发送多帧（窗口大小 W）。GBN（回退 N）和 SR（选择重传）是两种实现。", "score_points": ["停止-等待：信道利用率低", "滑动窗口：连续发送", "GBN：累积确认", "SR：单独确认重传", "窗口大小限制"], "difficulty": "较难", "tags": ["滑动窗口", "流量控制"]},
        {"title": "介质访问控制", "content": "MAC 子层协议：信道划分（FDM/TDM/CDMA）、随机访问（ALOHA/CSMA/CA）、轮询访问（令牌）。以太网用 CSMA/CD。无线局域网用 CSMA/CA + RTS/CTS。", "score_points": ["TDMA 时分，FDMA 频分", "CDMA 码分，WDMA 波分", "ALOHA：纯随机", "CSMA：先听后发", "CSMA/CD：冲突检测（有线）", "CSMA/CA：避免冲突（无线）"], "difficulty": "较难", "tags": ["MAC", "CSMA"]},
        {"title": "交换机与 VLAN", "content": "交换机（Switch）：MAC 地址表，转发决策基于 MAC，实现独享带宽。VLAN（虚拟局域网）：在同一物理 LAN 上划分多个逻辑 LAN，隔离广播域。Trunk 链路承载多 VLAN 流量。", "score_points": ["MAC 地址表学习", "交换转发/泛洪/丢弃", "VLAN 隔离广播域", "Trunk：802.1Q 标签", "VLAN 间通信：单臂路由/三层交换", "生成树协议：避免环路"], "difficulty": "中等", "tags": ["交换机", "VLAN"]},
        {"title": "PPP 协议与 HDLC", "content": "PPP（Point-to-Point Protocol）：点对点链路层协议，用于拨号、串口通信。三组件：LCP（链路控制）、NCP（网络控制）、认证（CHAP/PAP）。HDLC：高级数据链路控制，面向比特。", "score_points": ["PPP 三组件：LCP/NCP/认证", "CHAP 挑战握手", "PAP 密码明文", "HDLC 帧格式：标志+地址+控制+信息+FCS", "位填充法", "零比特填充"], "difficulty": "中等", "tags": ["PPP", "HDLC"]},
    ],
    "cn_network": [
        {"title": "IP 数据报与分片", "content": "IPv4 数据报格式：版本+首部长度+服务类型+总长度+标识+标志+片偏移+TTL+协议+首部校验和+源/目的 IP+选项+数据。分片：当 MTU 不足时，将大数据报分成多个小片，每片独立传输，偏移量以 8 字节为单位。", "score_points": ["首部 20 字节固定", "总长度 16 位 ≤ 65535", "TTL：防环路", "协议字段：TCP=6, UDP=17, ICMP=1", "片偏移：13 位，单位 8 字节", "首部校验和：仅校验首部", "MF=1 还有分片，MF=0 末片"], "difficulty": "中等", "tags": ["IP数据报", "分片"]},
        {"title": "ARP 协议", "content": "ARP（Address Resolution Protocol）：将 IP 地址解析为 MAC 地址。同局域网：ARP 广播询问，IP 拥有者单播响应。跨网段：ARP 找默认网关 MAC。", "score_points": ["ARP 请求：广播", "ARP 响应：单播", "ARP 缓存表：老化时间", "跨网段：ARP 找网关", "ARP 欺骗：安全隐患"], "difficulty": "基础", "tags": ["ARP", "地址解析"]},
        {"title": "ICMP 协议", "content": "ICMP（Internet Control Message Protocol）：差错报告（终点不可达、超时）和网络询问（ping/traceroute）。封装在 IP 数据报中。", "score_points": ["ICMP 差错报告", "ICMP 询问：回显请求/应答", "ping：测试连通性", "traceroute：TTL 探测路径", "终点不可达：网络/主机/协议/端口", "时间超过：TTL=0"], "difficulty": "中等", "tags": ["ICMP", "ping"]},
        {"title": "路由算法与协议", "content": "路由算法：距离向量（RIP，贝尔曼-福特算法）、链路状态（OSPF，Dijkstra 最短路）、路径向量（BGP）。内部网关协议 IGP（RIP/OSPF），外部网关协议 EGP（BGP）。", "score_points": ["RIP：跳数≤15，30s 更新", "OSPF：链路状态，洪泛 LSDB", "BGP：路径向量，AS 间", "AS：自治系统", "默认网关：0.0.0.0/0", "收敛：路由表稳定"], "difficulty": "较难", "tags": ["路由", "OSPF", "BGP"]},
        {"title": "DHCP 协议", "content": "DHCP（Dynamic Host Configuration Protocol）：动态分配 IP 地址。流程：Discover（广播）→ Offer（服务器响应）→ Request（客户端请求）→ ACK（确认）。", "score_points": ["DHCP Discover：广播", "DHCP Offer：服务器响应", "DHCP Request：客户端请求", "DHCP ACK：确认分配", "租约时间", "续租过程"], "difficulty": "中等", "tags": ["DHCP", "动态分配"]},
    ],
    "cn_transport": [
        {"title": "UDP 协议", "content": "UDP（User Datagram Protocol）：无连接、不可靠、高效、首部 8 字节。适用：DNS、视频流、实时游戏。首部：源端口、目的端口、长度、校验和。", "score_points": ["无连接、不可靠", "首部 8 字节", "伪首部用于校验", "适合实时应用", "校验和可选", "面向报文"], "difficulty": "基础", "tags": ["UDP", "无连接"]},
        {"title": "TCP 协议", "content": "TCP（Transmission Control Protocol）：面向连接、可靠、字节流。三次握手建立连接、四次挥手释放连接。首部 ≥ 20 字节：端口、序号、确认号、标志位（SYN/ACK/FIN/RST/PSH/URG）、窗口、校验和、紧急指针。", "score_points": ["三次握手：SYN, SYN+ACK, ACK", "四次挥手：FIN, ACK, FIN, ACK", "序号：字节流编号", "确认号：期望收到下一个字节", "窗口：流量控制", "SYN=1 建立连接，FIN=1 释放"], "difficulty": "中等", "tags": ["TCP", "三次握手", "四次挥手"]},
        {"title": "TCP 拥塞控制", "content": "TCP 拥塞控制：慢启动（cwnd 从 1 MSS 指数增长至 ssthresh）、拥塞避免（线性增长）、快重传（3 次重复 ACK 立即重传）、快恢复（cwnd 减半后线性增长）。", "score_points": ["慢启动：指数增长", "拥塞避免：线性增长", "ssthresh 阈值切换", "快重传：3 次重复 ACK", "快恢复：cwnd 减半", "AIMD 算法：加性增乘性减"], "difficulty": "较难", "tags": ["拥塞控制", "慢启动"]},
        {"title": "TCP 流量控制", "content": "TCP 流量控制通过滑动窗口实现。接收方在 ACK 中告知窗口大小（rwnd），发送方根据 rwnd 调整发送速率。零窗口：接收方窗口=0 时发送方停止发送；坚持定时器定期探测窗口。", "score_points": ["rwnd：接收窗口", "cwnd：拥塞窗口", "发送窗口 = min(rwnd, cwnd)", "零窗口：停止发送", "坚持定时器：探测窗口", "Nagle 算法：减少小包"], "difficulty": "较难", "tags": ["流量控制", "滑动窗口"]},
    ],
    "cn_app": [
        {"title": "DNS 域名系统", "content": "DNS（Domain Name System）：将域名解析为 IP。层次结构：根域→顶级域（com/org/cn）→二级域→子域→主机。查询方式：递归（代理查询）和迭代（返回参考）。服务器：根域名、顶级域名、权威域名、本地域名。", "score_points": ["根域 → 顶级域 → 二级域", "递归 vs 迭代查询", "本地域名服务器", "权威域名服务器", "DNS 缓存", "资源记录 A/AAAA/MX/CNAME/NS"], "difficulty": "中等", "tags": ["DNS", "域名"]},
        {"title": "FTP 文件传输协议", "content": "FTP（File Transfer Protocol）：基于 TCP 的文件传输协议，使用两个连接：控制连接（21 端口）和数据连接（20 端口，主动模式/被动模式）。模式：ASCII 和 Binary。", "score_points": ["控制连接：21 端口", "数据连接：20 端口", "主动模式：服务器连客户端", "被动模式：客户端连服务器", "ASCII 模式 vs Binary 模式", "FTP 命令：USER/PASS/LIST/RETR/STOR"], "difficulty": "中等", "tags": ["FTP", "文件传输"]},
        {"title": "HTTP 与 HTTPS", "content": "HTTP（HyperText Transfer Protocol）：基于 TCP 的应用层协议，80 端口，无状态。请求方法：GET/POST/PUT/DELETE/HEAD。HTTPS = HTTP + SSL/TLS，443 端口，加密传输。", "score_points": ["HTTP 80 端口", "HTTPS 443 端口", "HTTP/1.1 持久连接", "HTTP/2 多路复用", "HTTPS 加密：SSL/TLS", "HTTP 方法：GET/POST/PUT/DELETE", "状态码：200/301/404/500"], "difficulty": "中等", "tags": ["HTTP", "HTTPS", "Web"]},
        {"title": "SMTP 与 POP3/IMAP", "content": "SMTP（Simple Mail Transfer Protocol）：邮件发送协议，25 端口。POP3（Post Office Protocol v3）：110 端口，下载邮件到本地。IMAP（Internet Message Access Protocol）：143 端口，同步服务器邮件。", "score_points": ["SMTP 发送 25 端口", "POP3 接收 110 端口", "IMAP 接收 143 端口", "POP3 下载后服务器可删", "IMAP 同步服务器", "MIME：邮件扩展"], "difficulty": "中等", "tags": ["SMTP", "POP3", "IMAP"]},
        {"title": "WebSocket", "content": "WebSocket：HTML5 开始提供的一种在单个 TCP 连接上进行全双工通信的协议。握手基于 HTTP Upgrade 头部，之后升级为 WebSocket 双向通信。适用：实时聊天、在线游戏、实时数据推送。", "score_points": ["全双工通信", "单 TCP 连接", "基于 HTTP 升级握手", "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key 验证"], "difficulty": "中等", "tags": ["WebSocket", "实时"]},
    ],
}

# ============================================================
# 通过文本替换更新每个 curriculum 文件
# ============================================================

def point_to_text(p, indent="        "):
    """把一个点序列化为 Python 字典字面量文本。"""
    import json
    j = json.dumps(p, ensure_ascii=False, separators=(', ', ': '))
    return indent + j.replace(': ', ': ')

def append_points_to_file(filepath, new_points_by_chapter):
    """读取文件，注入新点，写回。"""
    with open(filepath, 'r', encoding='utf-8') as f:
        src = f.read()
    # 解析时不能简单地用正则；改为逐章找到 "chapter_id": "xx" 后面对应的 "points": [...],
    # 然后在那个 ] 之前插入新元素
    import re
    for cid, new_points in new_points_by_chapter.items():
        # 找到 chapter_id 出现处
        cid_pat = re.compile(r'("chapter_id"\s*:\s*"' + re.escape(cid) + r'"\s*,)')
        m = cid_pat.search(src)
        if not m:
            print(f"  ! 未找到章节 {cid}")
            continue
        # 在该 chapter 块中找到 "points": [
        rest = src[m.end():]
        points_start = re.search(r'"points"\s*:\s*\[', rest)
        if not points_start:
            print(f"  ! {cid} 无 points 字段")
            continue
        # 找到与这个 [ 配对的 ]
        # 因为 [ 在 points 内不嵌套，简单找下一行的 ]
        i = points_start.end()
        # 找 ] 配对 - 简单找第一个 ] 即可（points 内部无嵌套方括号）
        close_idx = rest.find(']', i)
        if close_idx == -1:
            print(f"  ! {cid} 未找到 ]")
            continue
        # 在 ] 前插入新点
        # 找到 ] 之前的最后一个列表元素
        insert_pos = m.end() + close_idx
        # 先看 ] 前一个字符是什么（, 或其他）
        prev_char = src[insert_pos - 1]
        if prev_char != ',':
            # 没有逗号，需要加一个
            addition = ',\n'
        else:
            addition = '\n'
        # 生成新点文本
        new_text_chunks = []
        for p in new_points:
            t = point_to_text(p, indent="        ")
            new_text_chunks.append(t)
        addition += ',\n'.join(new_text_chunks)
        # 写入
        src = src[:insert_pos] + addition + '\n      ' + src[insert_pos:]
        print(f"  + {cid}: 追加 {len(new_points)} 个点")
    # 写回
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(src)

# ============================================================
# 主流程
# ============================================================
if __name__ == "__main__":
    print("=== 扩充 数据结构 ===")
    append_points_to_file(os.path.join(BASE, 'data', 'curriculum_ds.py'), DS_NEW)
    print("=== 扩充 计算机组成原理 ===")
    append_points_to_file(os.path.join(BASE, 'data', 'curriculum_co.py'), CO_NEW)
    print("=== 扩充 操作系统 ===")
    append_points_to_file(os.path.join(BASE, 'data', 'curriculum_os.py'), OS_NEW)
    print("=== 扩充 计算机网络 ===")
    append_points_to_file(os.path.join(BASE, 'data', 'curriculum_cn.py'), CN_NEW)

    # 重新加载模块以验证
    for m in ['curriculum_ds', 'curriculum_co', 'curriculum_os', 'curriculum_cn']:
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    import data.curriculum_ds as ds
    import data.curriculum_co as co
    import data.curriculum_os as os_mod
    import data.curriculum_cn as cn
    for name, m in [('ds', ds), ('co', co), ('os', os_mod), ('cn', cn)]:
        total = sum(len(c['points']) for c in m.CHAPTERS)
        print(f'  {name}: {len(m.CHAPTERS)} chapters, {total} points')
