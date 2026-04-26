import tkinter as tk
from tkinter import scrolledtext, messagebox
import socket
import threading
import time

# ==================== GLOBAL VARIABLES ====================
running = False
clients = []
udp_sockets = []   # Для корректного закрытия UDP сокетов


def log(text):
    timestamp = time.strftime("%H:%M:%S")
    log_text.insert(tk.END, f"[{timestamp}] {text}\n")
    log_text.see(tk.END)


# ====================== TCP FORWARD ======================
def handle_tcp_client(client_socket, dst_host, dst_port):
    try:
        remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote.connect((dst_host, dst_port))
        clients.extend([client_socket, remote])

        def forward(src, dst):
            while running:
                try:
                    data = src.recv(4096)
                    if not data:
                        break
                    dst.sendall(data)
                except:
                    break

        t1 = threading.Thread(target=forward, args=(client_socket, remote), daemon=True)
        t2 = threading.Thread(target=forward, args=(remote, client_socket), daemon=True)
        t1.start()
        t2.start()
    except Exception as e:
        log(f"TCP Error: {e}")
    finally:
        client_socket.close()


# ====================== UDP FORWARD ======================
def handle_udp_forward(src_host, src_port, dst_host, dst_port):
    udp_sock = None
    try:
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind((src_host, src_port))
        
        udp_sockets.append(udp_sock)  # Сохраняем для закрытия
        
        log(f"UDP Forward started: {src_host}:{src_port} → {dst_host}:{dst_port}")

        while running:
            try:
                data, addr = udp_sock.recvfrom(8192)
                if not data:
                    continue
                udp_sock.sendto(data, (dst_host, dst_port))
                
                # Получаем ответ
                try:
                    response, _ = udp_sock.recvfrom(8192, socket.MSG_DONTWAIT)
                    udp_sock.sendto(response, addr)
                except:
                    pass  # Нет ответа — нормально для некоторых UDP протоколов
            except:
                if running:
                    continue
    except Exception as e:
        log(f"UDP Error: {e}")
    finally:
        if udp_sock and udp_sock in udp_sockets:
            udp_sockets.remove(udp_sock)
        try:
            udp_sock.close()
        except:
            pass


# ====================== HTTP PROXY MODE ======================
def handle_http_client(client_socket, dst_host, dst_port):
    try:
        request = client_socket.recv(4096)
        if not request:
            return

        request_str = request.decode(errors='ignore')

        if request_str.startswith("CONNECT"):
            try:
                host_port = request_str.split(" ")[1]
                target_host, target_port = host_port.split(":")
                target_port = int(target_port)
            except:
                target_host, target_port = dst_host, dst_port

            client_socket.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            log(f"HTTPS Tunnel: {target_host}:{target_port}")
            handle_tcp_client(client_socket, target_host, target_port)
            return
        else:
            handle_tcp_client(client_socket, dst_host, dst_port)

    except Exception as e:
        log(f"HTTP Error: {e}")


# ====================== START / STOP ======================
def start_proxy():
    global running

    if running:
        log("Proxy is already running!")
        return

    # Очистка перед запуском
    clients.clear()
    udp_sockets.clear()

    src_host = entry_src_host.get().strip()
    src_port = entry_src_port.get().strip()
    dst_host = entry_dst_host.get().strip()
    dst_port = entry_dst_port.get().strip()

    if not all([src_host, src_port, dst_host, dst_port]):
        messagebox.showwarning("Warning", "Please fill all fields!")
        return

    try:
        src_port = int(src_port)
        dst_port = int(dst_port)
    except:
        messagebox.showerror("Error", "Ports must be numbers!")
        return

    tcp_enabled = var_tcp.get()
    udp_enabled = var_udp.get()
    http_enabled = var_http.get()

    if not tcp_enabled and not udp_enabled:
        messagebox.showwarning("Warning", "Select at least TCP or UDP!")
        return

    running = True
    btn_start.config(state="disabled")
    btn_stop.config(state="normal")

    log(f"Starting proxy: {src_host}:{src_port} → {dst_host}:{dst_port}")
    if http_enabled:
        log("Mode: HTTP/HTTPS Proxy (CONNECT)")

    # TCP
    if tcp_enabled:
        def tcp_server():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind((src_host, src_port))
                server.listen(15)
                log(f"TCP listening on {src_host}:{src_port}")

                while running:
                    try:
                        client, addr = server.accept()
                        log(f"Client connected: {addr[0]}:{addr[1]}")
                        handler = handle_http_client if http_enabled else handle_tcp_client
                        threading.Thread(target=handler, args=(client, dst_host, dst_port), daemon=True).start()
                    except:
                        break
            except Exception as e:
                log(f"TCP Server Error: {e}")
            finally:
                server.close()

        threading.Thread(target=tcp_server, daemon=True).start()

    # UDP
    if udp_enabled:
        threading.Thread(target=handle_udp_forward, 
                        args=(src_host, src_port, dst_host, dst_port), 
                        daemon=True).start()

    log("Proxy started successfully!")


def stop_proxy():
    global running
    running = False
    
    log("Stopping proxy...")

    # Закрываем все клиенты
    for sock in clients[:]:
        try:
            sock.close()
        except:
            pass
    clients.clear()

    # Закрываем UDP сокеты
    for sock in udp_sockets[:]:
        try:
            sock.close()
        except:
            pass
    udp_sockets.clear()

    # Небольшая пауза для освобождения портов Windows
    time.sleep(0.8)

    btn_start.config(state="normal")
    btn_stop.config(state="disabled")
    log("Proxy stopped.")


# ====================== GUI ======================
root = tk.Tk()
root.title("Simple Proxy Forwarder")
root.geometry("620x460")
root.resizable(False, False)

tk.Label(root, text="Simple Proxy Forwarder", font=("Arial", 14, "bold")).pack(pady=8)

frame = tk.Frame(root)
frame.pack(pady=8, padx=20, fill="x")

tk.Label(frame, text="Source Host:", font=("Arial", 10)).grid(row=0, column=0, sticky="w", pady=4)
entry_src_host = tk.Entry(frame, width=40, font=("Arial", 10))
entry_src_host.grid(row=0, column=1, pady=4, padx=8)
entry_src_host.insert(0, "127.0.0.1")

tk.Label(frame, text="Source Port:", font=("Arial", 10)).grid(row=1, column=0, sticky="w", pady=4)
entry_src_port = tk.Entry(frame, width=40, font=("Arial", 10))
entry_src_port.grid(row=1, column=1, pady=4, padx=8)
entry_src_port.insert(0, "55555")

tk.Label(frame, text="Destination Host:", font=("Arial", 10)).grid(row=2, column=0, sticky="w", pady=4)
entry_dst_host = tk.Entry(frame, width=40, font=("Arial", 10))
entry_dst_host.grid(row=2, column=1, pady=4, padx=8)
entry_dst_host.insert(0, "11.22.33.44")

tk.Label(frame, text="Destination Port:", font=("Arial", 10)).grid(row=3, column=0, sticky="w", pady=4)
entry_dst_port = tk.Entry(frame, width=40, font=("Arial", 10))
entry_dst_port.grid(row=3, column=1, pady=4, padx=8)
entry_dst_port.insert(0, "55555")

options_frame = tk.LabelFrame(root, text="Forwarding Modes", font=("Arial", 10, "bold"), padx=15, pady=8)
options_frame.pack(pady=10, fill="x", padx=20)

var_tcp = tk.BooleanVar(value=True)
var_udp = tk.BooleanVar(value=False)
var_http = tk.BooleanVar(value=False)

tk.Checkbutton(options_frame, text="TCP Forwarding", variable=var_tcp, font=("Arial", 10)).pack(anchor="w")
tk.Checkbutton(options_frame, text="UDP Forwarding", variable=var_udp, font=("Arial", 10)).pack(anchor="w")
tk.Checkbutton(options_frame, text="HTTP/HTTPS Proxy Mode (CONNECT)", variable=var_http, font=("Arial", 10)).pack(anchor="w")

btn_frame = tk.Frame(root)
btn_frame.pack(pady=12)

btn_start = tk.Button(btn_frame, text="▶ Start Proxy", width=18, height=2,
                      bg="#00aa00", fg="white", font=("Arial", 10, "bold"), command=start_proxy)
btn_start.pack(side="left", padx=12)

btn_stop = tk.Button(btn_frame, text="⛔ Stop Proxy", width=18, height=2,
                     bg="#aa0000", fg="white", font=("Arial", 10, "bold"), 
                     command=stop_proxy, state="disabled")
btn_stop.pack(side="left", padx=12)

tk.Label(root, text="Log:", font=("Arial", 10)).pack(anchor="w", padx=20)
log_text = scrolledtext.ScrolledText(root, height=12, font=("Consolas", 9))
log_text.pack(padx=20, pady=6, fill="both", expand=True)

log("Ready. Configure and start the proxy.")

root.mainloop()