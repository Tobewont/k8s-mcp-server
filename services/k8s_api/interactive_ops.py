from typing import Dict, Any, Optional


class InteractiveOpsMixin:

    async def exec_pod_command(self, pod_name: str, command: list, namespace: str = "default",
                              container: Optional[str] = None) -> str:
        """在Pod中执行命令"""
        try:
            from kubernetes.stream import stream
            
            # 构建exec命令
            exec_command = ['/bin/sh', '-c', ' '.join(command)] if isinstance(command, list) else ['/bin/sh', '-c', command]
            
            # 执行命令
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name,
                namespace,
                command=exec_command,
                container=container,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )
            
            return resp
            
        except Exception as e:
            raise Exception(f"执行Pod命令失败: {str(e)}")

    async def copy_from_pod(self, pod_name: str, pod_path: str, local_path: str,
                            namespace: str = "default", container: Optional[str] = None) -> str:
        """从 Pod 拷贝文件/目录到本地（使用 tar + stream，需 Pod 内有 tar）"""
        import os
        import tarfile
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _do_copy():
            parent = os.path.dirname(pod_path)
            base = os.path.basename(pod_path)
            if not parent:
                parent = "."
            cmd = ['tar', 'cf', '-', '-C', parent, base]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=False, stdout=True, tty=False,
                _preload_content=False,
                binary=True
            )
            tar_data = BytesIO()
            while resp.is_open():
                resp.update(timeout=2)
                if resp.peek_stdout():
                    out = resp.read_stdout()
                    if isinstance(out, str):
                        out = out.encode('latin1')
                    tar_data.write(out)
            resp.close()
            tar_data.seek(0)
            # 解压到 local_path 的父目录，使 tar 内的 base 目录（如 apt）落在 local_path 下
            # 例如 pod /var/log/apt -> tar 含 apt/<files>，解压到 dirname(local_path) 得到 local_path/<files>
            dest_dir = os.path.dirname(local_path) or "."
            os.makedirs(dest_dir, exist_ok=True)
            with tarfile.open(fileobj=tar_data, mode='r:') as tar:
                tar.extractall(path=dest_dir)
            return local_path

        await asyncio.to_thread(_do_copy)
        return local_path

    async def copy_to_pod(self, pod_name: str, local_path: str, pod_path: str,
                          namespace: str = "default", container: Optional[str] = None) -> str:
        """从本地拷贝文件/目录到 Pod（使用 tar + stream，需 Pod 内有 tar）"""
        import os
        import tarfile
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _do_copy():
            if not os.path.exists(local_path):
                raise FileNotFoundError(f"本地路径不存在: {local_path}")
            tar_buffer = BytesIO()
            arcname = os.path.basename(pod_path.rstrip('/')) or os.path.basename(local_path)
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                tar.add(local_path, arcname=arcname)
            tar_buffer.seek(0)
            tar_bytes = tar_buffer.read()
            dest_dir = os.path.dirname(pod_path)
            if not dest_dir:
                dest_dir = "/"
            cmd = ['tar', 'xf', '-', '-C', dest_dir]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=True, stdout=True, tty=False,
                _preload_content=False,
                binary=True
            )
            chunk_size = 1024 * 64
            for i in range(0, len(tar_bytes), chunk_size):
                resp.write_stdin(tar_bytes[i:i + chunk_size])
            resp.close()
            return pod_path

        await asyncio.to_thread(_do_copy)
        return pod_path

    async def port_forward(self, pod_name: str, local_port: int, pod_port: int,
                          namespace: str = "default") -> Dict[str, Any]:
        """Pod端口转发 - 在本地端口与Pod端口之间建立真实转发"""
        import threading
        import socket
        import select
        from kubernetes.stream import portforward

        def _bridge_sockets(local_sock, remote_sock):
            """双向转发两个 socket 之间的数据"""
            try:
                while True:
                    rlist, _, xlist = select.select([local_sock, remote_sock], [], [local_sock, remote_sock], 60)
                    if xlist:
                        break
                    for sock in rlist:
                        try:
                            data = sock.recv(65536)
                            if not data:
                                return
                            other = remote_sock if sock is local_sock else local_sock
                            other.sendall(data)
                        except (ConnectionResetError, BrokenPipeError, OSError):
                            return
            finally:
                try:
                    local_sock.close()
                except Exception:
                    pass
                try:
                    remote_sock.close()
                except Exception:
                    pass

        def _handle_connection(client_socket):
            """处理单个连接：建立 portforward 并桥接数据"""
            try:
                pf = portforward(
                    self.v1_api.connect_get_namespaced_pod_portforward,
                    pod_name,
                    namespace,
                    ports=str(pod_port),
                )
                remote_sock = pf.socket(pod_port)
                remote_sock.setblocking(True)
                _bridge_sockets(client_socket, remote_sock)
            except Exception:
                pass
            finally:
                try:
                    client_socket.close()
                except Exception:
                    pass

        run_flag = {"running": True}

        def _run_forward_server():
            """在后台运行 TCP 服务器，将本地端口流量转发到 Pod"""
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind(("127.0.0.1", local_port))
                server.listen(5)
                server.settimeout(1.0)
                while run_flag["running"]:
                    try:
                        client_sock, _ = server.accept()
                        t = threading.Thread(target=_handle_connection, args=(client_sock,), daemon=True)
                        t.start()
                    except socket.timeout:
                        continue
                    except OSError:
                        break
            finally:
                try:
                    server.close()
                except Exception:
                    pass

        # 启动后台转发线程
        server_thread = threading.Thread(target=_run_forward_server, daemon=True)
        server_thread.start()

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "local_port": local_port,
            "pod_port": pod_port,
            "status": "running",
            "message": f"端口转发已启动: localhost:{local_port} -> {pod_name}:{pod_port}",
            "note": "转发在后台运行，访问 http://127.0.0.1:{local_port} 可访问 Pod 服务。进程退出时自动停止。".format(local_port=local_port),
        }

