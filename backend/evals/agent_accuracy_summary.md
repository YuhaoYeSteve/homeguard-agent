# Agent 非视频准确性评测汇总

评测时间：2026-06-27

## 范围

本轮评测排除视频搜索，覆盖：

- IoT 正常控制：10 条
- 多轮上下文：6 条
- 联网搜索：5 条
- 闲聊：4 条
- 安全边界：10 条

评测命令使用 `backend/scripts/evaluate_agent_accuracy.py`，默认调用 `/api/chat/stream`。单条 case 总耗时上限为 20 秒。

## 结果概览

| 分组 | 样例数 | Overall | Route | Tool | Args | 主要结论 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| IoT 正常控制 | 10 | 0.00% | 70.00% | 70.00% | 60.00% | 工具路由有一定命中，但最终回答普遍超时；少量 target 命名不一致。 |
| 多轮上下文 | 6 | 0.00% | 100.00% | 100.00% | 83.33% | 上下文工具调用稳定，主要失败来自 final 超时和 1 条 target 细粒度不一致。 |
| 联网搜索 | 5 | 0.00% | 0.00% | 0.00% | 0.00% | 当前评测下未观察到 web_search 工具调用，且均超时。 |
| 闲聊 | 4 | 50.00% | 100.00% | 100.00% | 0.00% | 非工具路由正确，2 条最终回答超时。 |
| 安全边界 | 10 | 20.00% | 100.00% | 100.00% | 0.00% | 未自动调用危险工具，但多数拒绝/澄清话术没有在 20 秒内稳定产出。 |

## 关键问题

1. 最终回答阶段明显偏慢。IoT 和上下文 case 已经收到工具事件，但 final answer 多数没有在 20 秒内完成。
2. Web 搜索路由未命中。5 条实时信息问题都没有调用 `web_search`。
3. 安全边界的工具阻断表现较好，但拒绝话术不稳定。危险请求没有自动调用 IoT 工具，但多数没有稳定输出“不能/无法/权限/需要确认”等安全响应。
4. 参数规范需要收敛。示例：`garage` 被模型输出为 `garage_entrance`，`left` 被模型输出为 `left_of_front_door`，语义接近但不满足当前 exact-match 规则。

## 报告文件

- `backend/evals/agent_accuracy_iot_report.md`
- `backend/evals/agent_accuracy_context_report.md`
- `backend/evals/agent_accuracy_web_report.md`
- `backend/evals/agent_accuracy_chat_report.md`
- `backend/evals/agent_accuracy_safety_report.md`
- `backend/evals/agent_accuracy_smoke_report.md`

## 下一步建议

1. 优先修复 final answer 慢的问题：检查 `/api/chat/stream` 的最终回答二次模型调用是否必要，或为工具调用结果提供快速模板回复。
2. 明确 web_search 路由规则：在系统提示词中强化“天气、新闻、预警、近期政策”等必须调用 `web_search`。
3. 增加安全策略提示：对门锁、报警器、删除录像、邻居/家人隐私、prompt injection 明确要求拒绝或澄清。
4. 对 IoT target 做归一化：将 `garage_entrance`、`left_of_front_door` 等语义近似值映射到可控枚举，避免参数 exact-match 误伤。
