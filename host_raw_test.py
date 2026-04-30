import socket, time, sys

# Test from the HOST (not container) to see if gateway accepts host connections
for ip in ['127.0.0.1']:
    print(f"--- Raw connect from HOST to {ip}:4001 ---")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5)
        s.connect((ip, 4001))
        print("TCP connected from host")
        s.send(b'API\x00\x00\x00\x00\x07v100..176')
        time.sleep(1)
        try:
            data = s.recv(1024)
            print(f"Received {len(data)} bytes: {data[:200]}")
        except socket.timeout:
            print("No response (timeout)")
        s.close()
    except Exception as e:
        print(f"Failed: {e}")
