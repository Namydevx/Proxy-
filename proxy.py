#!/usr/bin/python3
import socket, threading, select, sys, getopt, time, logging
from collections import defaultdict
from datetime import datetime

# CONFIG
LISTENING_ADDR = '0.0.0.0'
LISTENING_PORT = 8880
PASS = ''  # Kosongkan jika tidak ingin pakai password
BUFLEN = 16384
TIMEOUT = 60
DEFAULT_HOST = '127.0.0.1:22'
RESPONSE = 'HTTP/1.1 101 Switching Protocols\r\nContent-Length: 104857600000\r\n\r\n'
MAX_CONNECTIONS_PER_IP = 3

# GLOBAL TRACKING
active_ip_connections = defaultdict(int)
last_seen_ip = defaultdict(lambda: datetime.now())
ip_lock = threading.Lock()
monitor_mode = False

# Logging setup
logging.basicConfig(
    filename='proxy.log',
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class Server(threading.Thread):
    def __init__(self, host, port):
        super().__init__()
        self.running = False
        self.host = host
        self.port = port
        self.threads = []
        self.threadsLock = threading.Lock()

    def run(self):
        self.soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.soc.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.soc.settimeout(2)
        self.soc.bind((self.host, int(self.port)))
        self.soc.listen(100)
        self.running = True

        logging.info(f"Server started on {self.host}:{self.port}")

        try:
            while self.running:
                try:
                    c, addr = self.soc.accept()
                    c.setblocking(1)
                except socket.timeout:
                    continue

                client_ip = addr[0]
                with ip_lock:
                    if active_ip_connections[client_ip] >= MAX_CONNECTIONS_PER_IP:
                        logging.warning(f"[{client_ip}] Too many active connections!")
                        try:
                            c.send(b"HTTP/1.1 429 Too Many Connections\r\n\r\n")
                            c.close()
                        except:
                            pass
                        continue
                    active_ip_connections[client_ip] += 1
                    last_seen_ip[client_ip] = datetime.now()

                conn = ConnectionHandler(c, self, addr, client_ip)
                conn.start()
                self.addConn(conn)
        finally:
            self.running = False
            self.soc.close()
            logging.info("Server stopped.")

    def addConn(self, conn):
        with self.threadsLock:
            if self.running:
                self.threads.append(conn)

    def removeConn(self, conn):
        with self.threadsLock:
            if conn in self.threads:
                self.threads.remove(conn)

    def close(self):
        self.running = False
        with self.threadsLock:
            for c in list(self.threads):
                c.close()

class ConnectionHandler(threading.Thread):
    def __init__(self, client, server, addr, ip=None):
        super().__init__()
        self.client = client
        self.server = server
        self.addr = addr
        self.ip = ip or addr[0]
        self.clientClosed = False
        self.targetClosed = True
        self.client_buffer = b''

    def close(self):
        if not self.clientClosed:
            try: self.client.shutdown(socket.SHUT_RDWR)
            except: pass
            try: self.client.close()
            except: pass
            self.clientClosed = True

        if not self.targetClosed:
            try: self.target.shutdown(socket.SHUT_RDWR)
            except: pass
            try: self.target.close()
            except: pass
            self.targetClosed = True

        with ip_lock:
            if active_ip_connections[self.ip] > 0:
                active_ip_connections[self.ip] -= 1
            if active_ip_connections[self.ip] == 0:
                active_ip_connections.pop(self.ip, None)
                last_seen_ip.pop(self.ip, None)

    def run(self):
        log_prefix = f"[{self.ip}]"
        try:
            self.client_buffer = self.client.recv(BUFLEN)
            hostPort = self.findHeader(self.client_buffer, b'X-Real-Host') or DEFAULT_HOST.encode()

            if self.findHeader(self.client_buffer, b'X-Split'):
                self.client.recv(BUFLEN)

            passwd = self.findHeader(self.client_buffer, b'X-Pass')
            if PASS and passwd != PASS.encode():
                self.client.send(b'HTTP/1.1 400 WrongPass!\r\n\r\n')
                logging.warning(f"{log_prefix} Wrong password")
                return

            if not (hostPort.startswith(b'127.0.0.1') or hostPort.startswith(b'localhost') or PASS == ''):
                self.client.send(b'HTTP/1.1 403 Forbidden!\r\n\r\n')
                logging.warning(f"{log_prefix} Forbidden host: {hostPort.decode()}")
                return

            self.method_CONNECT(hostPort, log_prefix)

        except Exception as e:
            logging.error(f"{log_prefix} Connection error: {e}")
        finally:
            self.close()
            self.server.removeConn(self)
            logging.info(f"{log_prefix} Connection closed")

    def findHeader(self, head, header):
        try:
            start = head.find(header + b': ')
            if start == -1: return b''
            end = head.find(b'\r\n', start)
            return head[start + len(header) + 2:end]
        except:
            return b''

    def connect_target(self, host):
        i = host.find(b':')
        if i != -1:
            port = int(host[i+1:])
            host = host[:i]
        else:
            port = 443

        info = socket.getaddrinfo(host.decode(), port)[0]
        self.target = socket.socket(info[0], info[1], info[2])
        self.target.connect(info[4])
        self.targetClosed = False

    def method_CONNECT(self, path, log_prefix):
        logging.info(f"{log_prefix} CONNECT {path.decode()}")
        self.connect_target(path)
        self.client.sendall(RESPONSE.encode())
        self.client_buffer = b''
        self.doCONNECT()

    def doCONNECT(self):
        sockets = [self.client, self.target]
        timeout_count = 0

        while True:
            r, _, e = select.select(sockets, [], sockets, 3)
            if e: break
            if r:
                for sock in r:
                    try:
                        data = sock.recv(BUFLEN)
                        if data:
                            (self.target if sock is self.client else self.client).sendall(data)
                            timeout_count = 0
                        else:
                            return
                    except:
                        return
            else:
                timeout_count += 1
                if timeout_count >= TIMEOUT:
                    return

def print_usage():
    print('Usage:')
    print('  proxy.py -p <port>')
    print('  proxy.py -b <bindAddr> -p <port>')
    print('  proxy.py --monitor')

def parse_args(argv):
    global LISTENING_ADDR, LISTENING_PORT, monitor_mode
    try:
        opts, _ = getopt.getopt(argv, "hb:p:", ["bind=", "port=", "monitor"])
        for opt, arg in opts:
            if opt in ("-b", "--bind"):
                LISTENING_ADDR = arg
            elif opt in ("-p", "--port"):
                LISTENING_PORT = int(arg)
            elif opt == "--monitor":
                monitor_mode = True
    except:
        print_usage()
        sys.exit(2)

def print_active_ips():
    with ip_lock:
        print("\n📊 Active IP Connections:")
        for ip, count in active_ip_connections.items():
            last_seen = last_seen_ip[ip].strftime('%Y-%m-%d %H:%M:%S')
            print(f"  {ip:<15} | {count} conn(s) | last seen: {last_seen}")
        print("-" * 40)

def main():
    parse_args(sys.argv[1:])

    if monitor_mode:
        try:
            while True:
                print_active_ips()
                time.sleep(10)
        except KeyboardInterrupt:
            print("\nStopped monitor.")
            sys.exit(0)

    print(f"\n:------ WebSocket Proxy by Namydev ------:")
    print(f"Listening on {LISTENING_ADDR}:{LISTENING_PORT}")
    print(":---------------------------------------:\n")

    server = Server(LISTENING_ADDR, LISTENING_PORT)
    server.start()

    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("Stopping server...")
        server.close()

if __name__ == '__main__':
    main()
