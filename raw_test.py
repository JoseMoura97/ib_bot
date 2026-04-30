import socket, time

# Raw socket test - see what IB Gateway actually sends back
for ip in ['172.18.0.1', '172.17.0.1']:
    print(f"\n--- Raw connect to {ip}:4001 ---")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, 4001))
        print("TCP connected")
        # IB API handshake: send version string
        s.send(b'API\x00\x00\x00\x00\x07v100..176')
        time.sleep(1)
        try:
            data = s.recv(1024)
            print(f"Received {len(data)} bytes: {data[:100]}")
        except socket.timeout:
            print("No response (timeout)")
        s.close()
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
