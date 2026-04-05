# 中文真实评测资产

本目录提供一套可直接用于真实环境评测的中文样本集：

1. 样本集：`evals/samples/customer_support_eval_zh.jsonl`

设计目标：

1. 覆盖 `knowledge_request`
2. 覆盖 `knowledge_gap`
3. 覆盖 `technical_issue` 的澄清分支
4. 覆盖 `technical_issue` 的信息充分分支
5. 覆盖 `commercial_policy_request` 的自动草稿与人工升级分支
6. 覆盖 `feedback_intake`
7. 覆盖 `unrelated`
8. 覆盖 `multi_intent`

推荐运行方式：

```bash
python scripts/run_real_eval.py ^
  --samples-path evals/samples/customer_support_eval_zh.jsonl ^
  --report-path .artifacts/evals/customer_support_eval_zh_report.json ^
  --rebuild-index
```

说明：

1. 该命令默认会关闭 Gmail，仅验证非 Gmail 主流程。
2. 真实评测默认复用运行时真实知识源，当前默认知识源为 `data/customer_support_knowledge_zh.txt`。
3. 报告会复用系统内建的 `response_quality`、`trajectory_evaluation`、`latency_metrics`、`resource_metrics`。
4. 如果真实模型出现误路由、过度升级、过度保守，这些都会直接体现在报告里，不会被 fake provider 掩盖。
