# 方法依据与工程取舍

更新：2026-11-16。本文记录合作网络基础定义；时序研究框架见 [研究基础](research-foundation.md)，关系推断的实际实现和验收见 [关系推断](relationship-inference.md)。

- [Newman: The structure of scientific collaboration networks](https://arxiv.org/abs/cond-mat/0007214)：以共同署名构建作者网络的基础参考。
- [Constructing bibliometric networks: A comparison between full and fractional counting](https://arxiv.org/abs/1607.02452)：全计数与分数计数的方法依据。
- [VOSviewer manual](https://www.vosviewer.com/documentation/Manual_VOSviewer_1.6.10.pdf)：每篇 n 人论文对每条作者对边贡献 1/(n-1)。这是链接计数，不是对论文贡献或质量的评估。每篇论文在整个无向图上的权重和为 n/2，并非恒为 1。
- [bibliometrix](https://www.bibliometrix.org/)：综合文献计量和主题演变对照工具；尚未集成其代码。
- [Quantifying patterns of research-interest evolution](https://arxiv.org/abs/1709.03319)：个人研究兴趣演变的相关研究，当前未复现该论文方法。三年窗口、JSD 和样本量阈值仍是待验证的设计选项。
- [NameClarifier](https://www.cs.cmu.edu/~sherryw/assets/pubs/2016-nameclarifier.pdf)：人工参与作者消歧的参考；当前由调用者提供确认后的作者 ID。

## 数据限制

[OpenAlex authentication](https://help.openalex.org/api/authentication/)：游标翻页需要 API Key，不能继续假定仅提供邮箱即可全量采集。

[OpenAlex authorships](https://help.openalex.org/data/authorships/)：列表结果可截断至前 100 个作者，单条记录最多保留 5000 个。在线采集器对截断列表请求单篇详情补全；仍存在 authors_count 大于实际列表长度的数据不会进入完整作者网络统计。若源数据本身已经丢失作者，程序无法自行恢复。

本地网页包含在线检索、采集任务、论文检索、时间网络和关系推断。SQLite 保存采集论文、任务及分析缓存；原始论文事件与推断层分开保存。历史截面按论文年份过滤，不把今天的累计引用指标当作历史数值。
