#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""IPv4 Traceroute，支持 ICMP 和 UDP 两种探测方式。

阅读顺序：traceroute() -> 发送函数 -> receiveOnePing() -> 输出函数。
配置集中在文件末尾：目标、等待时间、最多站数、每站次数、协议、名称查询。
每次只发送一份并等待对应回复；每站完成全部测量后再决定是否停止。
"""

from contextlib import ExitStack
import math
import os
import socket
import struct
import time



ICMP_ECHO_REQUEST = 8
ICMP_ECHO_REPLY = 0
ICMP_TIME_EXCEEDED = 11
ICMP_DEST_UNREACHABLE = 3
UDP_START_PORT = 33434  # 每份 UDP 探测使用一个不同的目标端口。


def checksum(data):

    csum = 0
    count_to = (len(data) // 2) * 2
    count = 0

    while count < count_to:
        value = data[count + 1] * 256 + data[count]
        csum = (csum + value) & 0xffffffff
        count += 2

    if count_to < len(data):
        csum = (csum + data[-1]) & 0xffffffff

    csum = (csum >> 16) + (csum & 0xffff)
    csum += csum >> 16
    answer = (~csum) & 0xffff
    answer = (answer >> 8) | ((answer << 8) & 0xff00)

    # !BBHHH 已按网络顺序打包，因此不再使用原 helper 末尾的 htons。
    return answer


def sendOnePing(icmpSocket, destinationAddress, ID, sequence, ttl):


    # 设置 IPv4 的 TTL；先用校验值 0 准备 ICMP 消息头。
    icmpSocket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, 0, ID, sequence)
    payload = struct.pack("!d", time.time())

    # 对消息头和内容一起计算校验值，再把结果填回消息头。
    real_checksum = checksum(header + payload)
    header = struct.pack(
        "!BBHHH", ICMP_ECHO_REQUEST, 0, real_checksum, ID, sequence
    )
    full_packet = header + payload


    # 只用 perf_counter() 的读数计算 RTT，不能与 payload 的时间混用。
    send_time = time.perf_counter()
    icmpSocket.sendto(full_packet, (destinationAddress, 0))
    # 通道留给接收函数使用，由总流程统一关闭。
    return send_time


def sendOneUDP(udpSocket, destinationAddress, destination_port, ttl):

    udpSocket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
    payload = struct.pack("!d", time.time())
    send_time = time.perf_counter()
    udpSocket.sendto(payload, (destinationAddress, destination_port))
    return send_time

def receiveOnePing(icmpSocket, destinationAddress, ID, sequence,
                   send_time, timeout=1, protocol="icmp",
                   source_port=None, destination_port=None):

    deadline = send_time + timeout

    while True:

        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            return None

        
        icmpSocket.settimeout(remaining)
        try:
            packet, address = icmpSocket.recvfrom(65535)
        except socket.timeout:
            return None
        
        received_time = time.perf_counter()


        ip_length = (packet[0] & 0x0f) * 4
        icmp_packet = packet[ip_length:]
        reply_type, code = icmp_packet[:2]

        # ICMP 探测到达目标：目标直接返回 Echo Reply。
        if protocol == "icmp" and reply_type == ICMP_ECHO_REPLY and code == 0:
            if address[0] != destinationAddress:
                continue
            _, _, _, reply_id, reply_sequence = struct.unpack(
                "!BBHHH", icmp_packet[:8]
            )
            matched = reply_id == ID and reply_sequence == sequence
            reached = True

        elif ((reply_type == ICMP_TIME_EXCEEDED and code == 0)
              or (protocol == "udp" and reply_type == ICMP_DEST_UNREACHABLE
                  and code == 3)):
            # 错误回复附带原消息的开头：原 IPv4 头 + 原 ICMP/UDP 头。
            # 外层错误头没有 Echo ID，必须检查里面引用的原消息。
            original_packet = icmp_packet[8:]
            original_destination = socket.inet_ntoa(original_packet[16:20])
            expected_protocol = (socket.IPPROTO_ICMP if protocol == "icmp"
                                 else socket.IPPROTO_UDP)
            if (original_packet[9] != expected_protocol
                    or original_destination != destinationAddress):
                continue
            original_ip_length = (original_packet[0] & 0x0f) * 4
            reply_header = original_packet[
                original_ip_length:original_ip_length + 8
            ]
            if protocol == "icmp":
                request_type, request_code, _, reply_id, reply_sequence = (
                    struct.unpack("!BBHHH", reply_header)
                )
                matched = (request_type == ICMP_ECHO_REQUEST and request_code == 0
                           and reply_id == ID and reply_sequence == sequence)
                reached = False
            else:
                # UDP 头是：源端口、目标端口、长度、校验值，各占 2 字节。
                reply_source, reply_destination, _, _ = struct.unpack(
                    "!HHHH", reply_header
                )
                matched = (reply_source == source_port
                           and reply_destination == destination_port)
                # UDP 没有 Echo Reply；目标返回“端口不可达”才算到达。
                reached = (reply_type == ICMP_DEST_UNREACHABLE
                           and address[0] == destinationAddress)
        else:
            continue

        # 只接受属于本次探测的回复；旧序号或旧端口的迟到回复继续忽略。
        if matched:
            rtt = received_time - send_time
            return address[0], rtt, reached


def printHop(ttl, replies):

    measurements = []
    received = 0
    for reply in replies:
        if reply is None:
            measurements.append("*")
        else:
            address, rtt, reached = reply
            label = " (destination)" if reached else ""
            measurements.append(f"{address} {rtt * 1000:.3f} ms{label}")
            received += 1

    # 每次测量各显示自己的地址，同一站的回复可能来自不同路由器。
    sent = len(replies)
    missing = sent - received
    print(f"{ttl:2d}  " + " | ".join(measurements)
          + f"  No reply: {missing}/{sent} ({missing / sent:.0%})", flush=True)
    return received


def printHostnames(addresses):

    print("\nResponding address -> hostname")
    for address in addresses:
        try:
            hostname = socket.gethostbyaddr(address)[0]
        except OSError:
            hostname = address
        print(f"{address} -> {hostname}")


def traceroute(host, timeout=1, max_hops=30, probes_per_hop=3,
               protocol="icmp", resolve_names=True):

    # 配置只在入口检查一次；次数/端口不能超过协议字段可表示的范围。
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite number greater than 0")
    if not isinstance(max_hops, int) or not 1 <= max_hops <= 255:
        raise ValueError("max_hops must be an integer from 1 to 255")
    if not isinstance(probes_per_hop, int) or probes_per_hop < 1:
        raise ValueError("probes_per_hop must be a positive integer")
    if protocol not in ("icmp", "udp"):
        raise ValueError('protocol must be "icmp" or "udp"')
    probe_limit = 65535 if protocol == "icmp" else 65536 - UDP_START_PORT
    if max_hops * probes_per_hop > probe_limit:
        raise ValueError("Too many probes for the sequence/UDP port range")

    # 1. 准备目标、唯一序号和统计。字典只记录每个回复地址一次。
    destinationAddress = socket.gethostbyname(host)
    ID = os.getpid() & 0xffff
    sequence = 0
    total_sent = 0
    total_received = 0
    responding_addresses = {}
    reached_destination = False
    print(f"Traceroute to {host} [{destinationAddress}], protocol: {protocol.upper()}")
    print(f"Maximum hops: {max_hops}; timeout: {timeout} seconds; "
          f"probes per hop: {probes_per_hop}")

    # 2. 两种模式都先创建 ICMP 接收通道；UDP 模式额外创建发送通道。
    # ExitStack 负责统一关闭已创建的通道，包括报错或 Ctrl+C 的情况。
    with ExitStack() as channels:
        icmpSocket = channels.enter_context(
            socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        )
        udpSocket = None
        source_port = None
        if protocol == "udp":
            udpSocket = channels.enter_context(
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            )
            udpSocket.bind(("", 0))  # 让操作系统分配一个本地端口，整次探测共用。
            source_port = udpSocket.getsockname()[1]

        # 3. 外层改变 TTL，内层完成这一站的全部测量。0
        for ttl in range(1, max_hops + 1):
            replies = []
            for _ in range(probes_per_hop):
                sequence += 1  # 每份消息一个新序号，不能把 TTL 直接当序号。
                icmpSocket.settimeout(timeout)
                destination_port = None
                if protocol == "icmp":
                    send_time = sendOnePing(
                        icmpSocket, destinationAddress, ID, sequence, ttl
                    )
                else:
                    # UDP 用目标端口区分每份探测，接收时与引用的原 UDP 头核对。
                    destination_port = UDP_START_PORT + sequence - 1
                    udpSocket.settimeout(timeout)
                    send_time = sendOneUDP(
                        udpSocket, destinationAddress, destination_port, ttl
                    )

                total_sent += 1
                reply = receiveOnePing(
                    icmpSocket, destinationAddress, ID, sequence, send_time,
                    timeout, protocol, source_port, destination_port
                )
                replies.append(reply)
                if reply is not None:
                    address, _, reached = reply
                    responding_addresses[address] = None
                    reached_destination = reached_destination or reached

            # 到达目标后仍完成当前站的测量，然后结束，不再增加 TTL。
            total_received += printHop(ttl, replies)
            if reached_destination:
                break

    # 4. 汇总探测未回应比例。它不等同于实际业务流量的丢包率。
    missing = total_sent - total_received
    print(f"\nSent: {total_sent}; matched replies: {total_received}; "
          f"no reply: {missing} ({missing / total_sent:.1%})")
    print("No-reply percentages describe these probes, not forwarding loss.")
    if reached_destination:
        print("Destination reached.")
    else:
        print("Maximum hop limit reached without a destination reply.")
        print("A silent hop does not prove that routing stopped.")

    # 5. 所有探测结束、通道关闭后再反查名称，不影响每份探测的 RTT/超时。
    # 该步骤会使用系统名称查询服务；不需要时将 resolve_names 设为 False。
    if resolve_names and responding_addresses:
        printHostnames(responding_addresses)
    return reached_destination


if __name__ == "__main__":
    # 配置区：修改这里即可，不需要改发送和接收函数。
    # 默认目标为本机；外部目标由负责测试的同学按课程要求选择。
    TARGET= "lancaster.ac.uk"
    TIMEOUT = 1
    MAX_HOPS = 30
    PROBES_PER_HOP = 3
    PROTOCOL = "icmp"  # 改成 "udp" 使用 UDP 探测。
    RESOLVE_NAMES = True  # False 表示只显示 IP，不反查名称。

    try:
        traceroute(TARGET, timeout=TIMEOUT, max_hops=MAX_HOPS,
                   probes_per_hop=PROBES_PER_HOP, protocol=PROTOCOL,
                   resolve_names=RESOLVE_NAMES)
    except PermissionError:
        print("Permission denied. On Windows, run the terminal as Administrator.")
    except socket.gaierror as error:
        print(f"Cannot find the destination address: {error}")
    except OSError as error:
        print(f"Network error: {error}")
    except ValueError as error:
        print(f"Invalid setting: {error}")
    except KeyboardInterrupt:
        print("\nStopped by user.")
