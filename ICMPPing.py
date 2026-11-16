#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import socket
import os
import sys
import struct
import time
import select
import binascii  


ICMP_ECHO_REQUEST = 8 #ICMP type code for echo request messages
ICMP_ECHO_REPLY = 0 #ICMP type code for echo reply messages


def checksum(string): 
	csum = 0
	countTo = (len(string) // 2) * 2  
	count = 0

	while count < countTo:
		thisVal = string[count+1] * 256 + string[count]
		csum = csum + thisVal 
		csum = csum & 0xffffffff  
		count = count + 2
	
	if countTo < len(string):
		csum = csum + string[len(string) - 1]
		csum = csum & 0xffffffff 
	
	csum = (csum >> 16) + (csum & 0xffff)
	csum = csum + (csum >> 16)
	answer = ~csum 
	answer = answer & 0xffff 
	answer = answer >> 8 | (answer << 8 & 0xff00)

	answer = socket.htons(answer)

	return answer
	

        # Return RTT in seconds; ping() converts it to milliseconds
        return received_time - sent_time
	
def sendOnePing(icmpSocket, destinationAddress, ID,sequence):
	# Build header with checksum = 0 
	header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, 0, ID, sequence)
	payload = struct.pack("!d", time.time())
	# Checksum covers the whole packet: header + payload
	real_checksum = socket.ntohs(checksum(header + payload))
	header = struct.pack("!BBHHH", ICMP_ECHO_REQUEST, 0, real_checksum, ID, sequence)
	full_packet = header + payload
	# Put the real checksum in and send (port 0: ICMP has no ports)
	icmpSocket.sendto(full_packet, (destinationAddress, 0))

	
def doOnePing(destinationAddress, timeout,sequence): 
	# Raw socket:build the ICMP packet
	my_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
	my_socket.settimeout(timeout)
	# ICMP ID is 16 bits, keep only the low 16 bits of the PID
	my_id = os.getpid() & 0xFFFF
	sendOnePing(my_socket, destinationAddress, my_id, sequence)
	# Returns RTT in seconds, or None on timeout
	rtt = receiveOnePing(my_socket, destinationAddress, my_id, sequence, timeout)
	my_socket.close()
	return rtt
	
	
def ping(host, timeout=1):
	# host may be a domain name; convert it to an IP first
	dest = socket.gethostbyname(host)
	print(f"Pinging {host} [{dest}]\n")

	sequence = 1
	while True:
		rtt = doOnePing(dest, timeout, sequence)
		if rtt is not None:
			print(f"64 bytes from {dest}: icmp_seq={sequence} time={rtt*1000:.1f} ms")
		else:
			print(f"64 bytes from {dest}: icmp_seq={sequence} timeout")
		sequence += 1
		time.sleep(1)
	
ping("lancaster.ac.uk")

