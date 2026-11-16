1. 团队与环境  
团队编号：Team15  
操作系统：Windows 11（64 位）。Python：3.14.8。测试工具：Wireshark 4.6.9，用于抓包和验证。  
在 Windows 上使用原始套接字 ICMP 需要管理员 PowerShell；如果没有提升权限，套接字创建会失败。

2. 运行方式  
工作目录：包含 ICMPPing.py 和 Traceroute.py 的项目根目录。  
运行 ICMP Ping（管理员 PowerShell）：python ICMPPing.py。在脚本中修改目标主机变量。按 Ctrl-C 停止。  
运行 Traceroute（管理员 PowerShell）：python Traceroute.py。参数（TARGET、TIMEOUT、MAX_HOPS、PROBES_PER_HOP、PROTOCOL、RESOLVE_NAMES）是文件顶部的常量。

3. 测试与发现  
任务 1.1 ICMPPing  
用例 1（正常）：环回测试（127.0.0.1）。预期：持续收到回显应答，RTT 很小。实际：RTT 约 0.3 ms；Wireshark 捕获到匹配的 Echo-Request/Echo-Reply 对（帧 11-12），ID 和序列号匹配。  
用例 2（正常）：外部主机测试（lancaster.ac.uk，148.88.65.80）。输入：ping lancaster.ac.uk。预期：收到有效回显应答，跨网络 RTT 合理。实际：收到回复，RTT 约为 246–250 ms。Wireshark 帧 67（请求）和帧 74（回复）显示 ID 和序列号匹配。时间与系统 ping 输出略有差异，这是可以接受的。  
用例 3（失败/超时）：不可达目标 192.0.2.1。预期：每次探测都超时（等待窗口内没有匹配回复；不能证明丢包位置）。实际：每个序列号都打印“timeout”；Wireshark 显示发出的请求没有任何回复。  
用例 4（边界/错误输入）：无效主机名“hello?”。预期：优雅处理 DNS 失败。实际：程序因 socket.gaierror 崩溃；目前未处理 DNS 错误。

任务 1.2 Traceroute  
用例 1（正常）：环回目标（127.0.0.1）。预期：在第 1 跳到达目标并终止。实际：在第 1 跳到达，RTT 有效；Wireshark 捕获到 TTL=1 的 echo-request/reply。  
用例 2（正常多跳）：lancaster.ac.uk。输入：跟踪到 lancaster.ac.uk，MAX_HOPS=30。预期：从 1 开始递增 TTL，收集中间 Time Exceeded 响应，收到目标 Echo Reply 后停止。可能出现静默跳（*）。实际：在第 26 跳到达目标。出现若干静默跳。我们的输出与 Windows tracert -d 大体一致。实现正确解析了 Time Exceeded ICMP 错误包内封装的原始 ICMP 头，用于探测匹配，而不是使用外层 ICMP 头字段。静默跳并不意味着路由中断。  
用例 3（边界：最大跳数限制）：lancaster.ac.uk，MAX_HOPS=5。输入：跟踪到 lancaster.ac.uk，MAX_HOPS=5。预期：第 5 跳后停止，不到达目标。实际：在第 5 跳后终止，并输出“Maximum hop limit reached without a destination reply”。  
用例 4（失败：不可达目标）：192.0.2.1，MAX_HOPS=10。预期：部分路由器回复，之后无响应，在 MAX_HOPS 停止。实际：前几跳有响应，之后静默；在第 10 跳终止。  
用例 5（边界：无效主机名）：“hello”。预期：报告 DNS 失败并干净退出。实际：打印“Cannot find the destination address”并以退出码 0 退出。  
用例 6（可选扩展：Windows 上的 UDP 协议模式）——输入：对 127.0.0.1 使用 UDP 模式 traceroute。——预期：收到 ICMP 端口不可达回复。——实际：所有探测都显示无回复。Wireshark 确认有发出的 UDP 包和传入的 ICMP 端口不可达消息。在 Windows 上，ICMP 错误通知会发送到 UDP 套接字，而不是我们的原始 ICMP 套接字，因此我们无法捕获它们；这是平台相关问题。

4. 局限性  
1. ICMPPing.py 没有捕获 DNS 异常；无效主机名会导致程序崩溃。  
2. Traceroute 的 UDP 探测模式在 Windows 上因操作系统套接字行为而失败；我们计划之后在 WSL / Linux 上验证。  
3. ICMPPing 未实现高级统计（最小/最大/平均 RTT 或丢包汇总）。  
4. 提交中显示的所有测试跟踪都是真实网络抓包；没有使用模拟跟踪。

5. 贡献与来源  
Wu Ziqi：实现 ICMPPing 的发送端逻辑，包括 ICMP 包构造和校验和计算。  
Zhou Zimeng：实现 ICMPPing 的接收端逻辑，包括 IP/ICMP 头解析、包过滤、ID 序列匹配和 RTT 计算。  
Fu Yuchen 和 Lin Yanxi：共同实现完整的 Traceroute 程序，包括 TTL 递增探测逻辑、ICMP Time Exceeded 错误包解析、跳点报告和终止条件。  
Li Changxing：收集、整理并注释所有测试证据，包括控制台输出和 Wireshark 抓包。  
Guo Jiaxin：集成代码组件、组织项目文件并撰写本 README 文档。  
复用材料：checksum() 辅助函数由 Moodle 项目骨架提供。其他逻辑为自行编写。使用 AI 辅助进行代码结构建议。所有生成的代码在提交前均已人工审查、测试，并对照 Wireshark 抓包和系统自带的 ping / tracert 工具进行验证。
