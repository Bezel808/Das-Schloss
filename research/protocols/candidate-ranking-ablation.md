# 固定预算的候选与排序消融

这是上一批开发结果之后新增的开发诊断，不能称作事先预测了这些结果。执行前固定八个已有开发队列与预算 20；不接触验证/测试。

两种已有查询策略：neighbor_degree（只查历史合作者）和 observed_degree（可扩展更远的已发现作者）。复用已有逐目标查询日志，不能重选目标、偷看完整图或增加查询。报告实际作者查询数和返回论文量，不将两种策略视为等传输成本。

两种候选范围：当前观测图的二跳人物（CN>0）与已发现的所有非历史合作者。用相同评分器、同一观测图分别排序，分开检验扩大候选与改变评分的作用。neighbor_degree 的图本来不超出二跳，因此其两种范围应相同，这是内部一致性检查。

评分：CN、Adamic–Adar、Resource Allocation、以目标为重启点的 Personalized PageRank。PPR 固定 alpha=.85、绝对 L1 误差上界 1e-10、最多 500 次迭代；不收敛时明确失败，不发布近似结果。PPR 权重分别为无权、共同论文数、时间衰减分数贡献 Σ 2^(-(t-year)/3)/(team_size-1)。所有事件均来自已返回的截止年之前论文；同篇论文只计一次。半衰期3年为固定开发选择，未扫描后择优。

PPR 是经典基线，不宣称新算法；其数值误差界不是对未观测图的保证，更不是未来合作概率或 CN 的严格排序证书。实现与独立 NetworkX 求解核对。

主要报告同候选范围下的并列期望 micro recall@10、候选覆盖、条件排序表现和正例目标 AP。未发现未来正例仍计入分母，全部八个域/年份分别发布，不事后挑选有利年份。

参考：Page, Brin, Motwani & Winograd, The PageRank Citation Ranking, 1999；[NetworkX 官方定义与求解说明](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html)。
