# CR-20261102-w01-process-state

- 提出者：W-01 测试准备。
- 类型：进程存活规范边界。
- 状态：草案，待协调者决定；未修改平台实现。

## 问题与实测

W-01 §5.1 规定只根据 `GetExitCodeProcess == 259` 返回存活。微软明确提醒：已经终止的进程也可以返回真实退出码 259，单独比较这个值会误判。[GetExitCodeProcess](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getexitcodeprocess)

本轮受控子进程执行 `os._exit(259)`，等待结束后保留进程对象句柄，得到：

```text
实际退出码：259
GetExitCodeProcess：259
WaitForSingleObject(handle, 0)：0（对象已 signaled）
```

另用当前规范的 `0x1000` 查询权限打开自己的进程，再等待该句柄，实测返回 `0xFFFFFFFF`、错误码 5。增加等待检测必须同时考虑 `SYNCHRONIZE` 权限，不能只加一个调用。[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)

## 方案

1. 以进程对象是否 signaled 为依据，明确增加所需等待权限，并保留拒绝访问时的保守行为。影响平台内部 WinAPI 调用，不改公开签名。
2. 保留仅查退出码的近似方案，但文档明确其局限，并决定该近似是否满足单实例与桥接恢复需求。不能将退出 259 的边界测试改成“预期存活”后仍宣称精确判活。

另需明确：PID 超过 DWORD 上界时应拒绝，避免截断后误查别的进程；查询函数失败时应抛错还是保守返回 True。

## 准备测试

覆盖当前进程、普通已退出子进程、退出码 259、无效与越界 PID。只有自己的受控子进程参与实验；所有成功打开的句柄均关闭。

- 关闭条件：上述语义与访问掩码已确定，测试与文档一致，句柄生命周期可核对。
- 决定：待填写。
