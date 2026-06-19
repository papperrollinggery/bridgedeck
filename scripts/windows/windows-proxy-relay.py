#!/usr/bin/env python3
"""TCP relay for WSL clients reaching a Windows loopback proxy."""
from __future__ import annotations

import argparse
import socket
import threading
import time

BUFFER_SIZE = 65536
WILDCARD_HOSTS = {"", "0.0.0.0", "::"}


def close_socket(sock: socket.socket | None) -> None:
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def pipe(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        close_socket(src)
        close_socket(dst)


def handle(client: socket.socket, target_host: str, target_port: int, connect_timeout: float) -> None:
    upstream: socket.socket | None = None
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=connect_timeout)
        client.settimeout(None)
        upstream.settimeout(None)
        for sock in (client, upstream):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        left = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
        right = threading.Thread(target=pipe, args=(upstream, client), daemon=True)
        left.start()
        right.start()
        left.join()
        right.join()
    except OSError:
        close_socket(client)
        close_socket(upstream)


def serve(listen_host: str, listen_port: int, target_host: str, target_port: int, connect_timeout: float) -> None:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((listen_host, listen_port))
    server.listen(128)
    print(
        f"BridgeDeck proxy relay listening on {listen_host}:{listen_port} "
        f"-> {target_host}:{target_port}",
        flush=True,
    )
    try:
        while True:
            try:
                client, _addr = server.accept()
            except OSError:
                time.sleep(0.2)
                continue
            threading.Thread(
                target=handle,
                args=(client, target_host, target_port, connect_timeout),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        pass
    finally:
        close_socket(server)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relay WSL traffic to a Windows loopback proxy.")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=17897)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, default=7897)
    parser.add_argument("--connect-timeout", type=float, default=10.0)
    parser.add_argument(
        "--allow-lan",
        action="store_true",
        help="Allow wildcard listeners such as 0.0.0.0. Use a firewall rule if enabled.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.listen_host in WILDCARD_HOSTS and not args.allow_lan:
        raise SystemExit(
            "Refusing to listen on all interfaces without --allow-lan. "
            "Use the WSL gateway host or pass --allow-lan intentionally."
        )
    serve(args.listen_host, args.listen_port, args.target_host, args.target_port, args.connect_timeout)


if __name__ == "__main__":
    main()
