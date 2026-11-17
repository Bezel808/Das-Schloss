# 完整作者查询下的共同邻居排序界与预算实验

## 信息条件

一次查询返回指定作者截至 t 的全部论文事件，完整性相对于选定数据源，而非现实世界全部论文。目标作者 f 必须先完成查询，因而其历史邻居集合 N(f) 已知；其他作者未经查询的缺边保留为未知。已查询作者所涉及的负边可由完整响应确定。后续响应若新增一篇本应出现在已完成查询中的论文，程序拒绝继续生成证书。

当前验证对象是 Benson 等发布的 DBLP 与 MAG-History 时间超图。该查询条件在冻结数据上可严格执行；在 OpenAlex 等在线来源中，分页完成不自动证明作者身份与源数据完整，迁移时必须单独检查。

## 可证明的分数界

对候选 v∉N(f)∪{f}，定义已观察的共同邻居数 L(v)。令 Q 为已完成查询的作者集合。

- 若 v∈Q，其全部邻居已知，U(v)=L(v)。
- 否则 U(v)=L(v)+|(N(f)\Q)\N_obs(v)|。
- 任意尚未发现候选的 CN 上界为 |N(f)\Q|。

证明：N(f) 已固定。每位已查询的邻居与 v 是否相连已经确定，任何已观察正边也固定。只有双方未查询、尚无正证据的邻居—候选边可以补充；每条最多贡献一个共同邻居。把这些边全部补上得到上界，全部不补得到下界，两者均与查询约束相容。因此这是所声明图补全集内的逐候选紧界，不需要猜测漏边概率或预算。

取当前按 L 排序的 k 个候选，若其中最小 L 严格大于所有外部候选 U 及未发现候选上界，则得到历史 CN top-k 集合证书。严格不等式避免将依赖 ID 的任意并列排序冒充可认证差异。这个证书不证明未来合作，也不证明导师身份。

测试枚举了一个小图的全部可行补全，核对上下界均能达到；还检查未来响应拒绝、未发现候选约束与查询范围。真实实验逐状态使用评价器私有完整历史图验证界和证书，策略无法读取该图或未来标签。

## 查询策略与基线

当前实现随机查询、观察度数优先、候选区间宽度优先、仅历史合作者查询（随机/按度）、均匀覆盖以及边界歧义加权覆盖。后两者把待查询边看成 N(f)×候选的未知矩阵：查询邻居揭示一行，查询候选揭示一列。加权策略只用当前区间与 top-k 边界计算权重，再选当前可消除未知权重最多的查询；另保留未发现候选的影响。

这是一项待检验的自适应启发式，尚未声称具有全局近似比或论文级新颖性。逐项 CN 紧界也不能冒充一般图模型的鲁棒认证。需进一步与既有认证、主动采样和学习方法比较：
- https://people.csail.mit.edu/dln/papers/link/paper.pdf
- https://arxiv.org/abs/1910.14356
- https://arxiv.org/abs/2207.10128
- https://www.cs.cornell.edu/~arb/papers/ScHoLP-PNAS-2018.pdf

## 可复现评测

```bash
.venv/bin/python research/fetch_temporal.py
.venv/bin/python research/prepare_temporal.py
.venv/bin/python research/temporal_benchmark.py --dataset coauth-DBLP --cutoff 2008 --targets 128
.venv/bin/python research/temporal_benchmark.py --dataset coauth-MAG-History --cutoff 2008 --targets 128
```

队列仅依赖截至 t 的活跃程度和历史邻居，通过固定哈希顺序抽取；不能按未来是否发生合作筛人。预测 t+1 的新边，历史已出现人物与冷启动人物分别统计，重复合作单独评测。所有预算 0/5/10/20/40 保持同一目标分母；查询前沿耗尽时保留最后状态，不从大预算结果中丢人。

报告包括共同邻居、Adamic–Adar、Resource Allocation、Preferential Attachment、EdgeBank 和既有合作次数。后两种方法在新边上没有区分力，仍如实报告。全部已知未来正例进入 recall 分母，即使未进入候选集；不通过随意抽取负例报告漂亮的 accuracy。

逐目标查询顺序与结果保存在忽略入 Git 的 data/research/temporal/runs；汇总、完整数据哈希、实现哈希与队列写入 research/results。当前只有开发段结果，尚未启用最终留出。已完成轻量 logistic 的时间开发消融和配对目标 bootstrap；跨年份泛化、等实际成本及高阶预测仍未完成。冻结选择后才能解锁验证和最终评测。

新增实验结果见 research/results/*author-query-cn-3.json、forecast-ml-coauth-DBLP-2008.json 和 acquisition-paired-development.json。当前没有证实歧义加权优于仅查询历史合作者；模型与方法均未获生产预测资格。网页「实验验收」展示同一批真实结果。
