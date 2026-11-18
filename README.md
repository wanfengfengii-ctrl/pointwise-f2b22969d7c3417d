# 水质巡检班复测采集

值班员从当天复测清单取得工单、通道及每张票据允许完成的时窗，从班前口径表取得换算参数。工单共用一台串行选路器。质控员凭成功收据确认本批已齐，再按批次号把读数、实际采样证据及超阈项交给下一班。

## 一次班次

1. 调用 `Catalog.profile(revision_id, scales)` 登记通道口径，例如 `{"A": (2, 1), "B": (2, 1)}`。参数是整数倍率和偏置。原样重登返回同一修订号，同号异内容拒绝。
2. 调用 `Catalog.issue(order_id, revision_id, tickets)` 固定工单。以列表或元组提供一至八张 `(ticket_id, channel, opens_at, closes_at)`，原输入顺序即交班顺序。票据 ID 全单唯一。窗口是 0 至 600 秒的整数闭区间，限制完成时刻。相同内容可重登。错误字段、未知引用或内容冲突抛出 `OrderInputError`。`get_order(order_id)` 返回冻结工单，未登记时抛出 `OrderNotFound`。
3. 调用 `initialize_archive(path)` 准备 SQLite 文件库。初始化可重复执行，保留已封存数据和用户表。班次目录保存在内存中，封存批次包含跨进程复核所需的完整工单和口径。新口径用新修订号登记。
4. 用 `RecordedPort(DeviceState(channel, now, stable_at), recording)` 接入录制。设备钟从运行原点计整秒，`None` 表示初始未选通道。`run(catalog, order_id, device, path)` 从实际快照判定完整可行后缀，再发出一个动作。切换和采样名义各用一秒，切换实际完成一秒以后才能采。等待允许。如窗口下界为 L，最早开始为设备可用秒、稳定秒和 L−1 的最大值。
5. 按实际回执继续。切换、等待、采样的回执允许比名义晚。每次回执后重新判断尚待采的票据。实际样本须匹配本票通道，开始时已稳定，实际完成落在闭区间。同通道的不同票据各有独立采样。换算使用本工单的原始整数计数乘冻结倍率再加偏置，单位为毫单位。
6. 样本齐备后，`run` 原子封存并返回含 `batch_id` 和 `receipt_id` 的 `SuccessReceipt`。同工单的另一次成功采集获得独立批次。失败抛出 `CaptureFailure`，其 `code` 区分 `unknown_order`、`no_feasible_suffix`、`invalid_receipt`、`invalid_observation`、`device_error`、`batch_integrity` 和 `commit_failed`。失败不发布本轮成果，旧批次可读。`before_commit` 是可选的提交前测试钩子，接收待提交收据，抛错即回滚。
7. 调用 `read(path, batch_id)` 查得冻结工单、收据及按原票序排列的样本。样本保留实际通道、起止秒、原始计数和换算值。未知批次抛出 `BatchNotFound`。关闭并重开库或登记新修订后，同一批次读值不变。
8. 调用 `report(path, batch_id, threshold)` 逐票复核。读数严格大于阈值才标记超阈。阈值及换算输入用整数，空值、布尔值和浮点值不合格。阈值非法抛出 `InvalidThreshold`。`render_handoff(result)` 输出适合离线交接的制表符分隔文本。普通整数以十进制呈现，超过解释器十进制转换限制的整数以带符号的十六进制呈现。

## 录制和复现

`RecordedAction(kind, key, raw_count=..., extra_seconds=..., start_delay=...)` 逐条指定动作。`switch` 的 key 是目标通道，`sample` 的 key 是票据 ID，`wait` 的 key 是等待目标秒。未显式录制的等待按设备当前秒和等待目标生成回执，其他动作按录制次序匹配。`extra_seconds` 延长实际完成秒。录制也可用 `actual_channel`、`actual_ticket_id` 或 `error` 表达真实回执偏差与设备报错。`RecordedPort.trace` 保留已尝试的设备动作、请求秒、回执和错误。排程与回放均使用整数设备钟。

初始选中 A 且已稳定，A 票窗口 [0,5]，B 票窗口 [0,4]。先 A 后 B 时，A 在 [0,1] 取样，B 在 [1,2] 切换、等到第 3 秒、在 [3,4] 取样。先 B 会使 A 最早在第 6 秒完成。原始计数 3、4 采用倍率 2、偏置 1，得 7、9。按阈值 7 交班时，仅 B 超阈。

## 运行

使用 Python 3.11 标准库，在仓库根目录执行。

```sh
python3 -B -m unittest discover -s tests -v
python3 -B -m water_shift_demo
```

完整回归包含口径固定、工单拒绝、同通道独立取样、等待、实际延迟、故障终止、整批回滚、重开和严格阈值。演示沿实际采集入口运行上述两通道样例，核对真实动作与归档结果后打印场景证据和交班文本。回归和演示使用独立临时库。
