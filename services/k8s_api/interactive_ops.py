from typing import Dict, Any, List, Optional

from config import MAX_POD_FILE_SIZE


class InteractiveOpsMixin:

    async def exec_pod_command(self, pod_name: str, command: list, namespace: str = "default",
                              container: Optional[str] = None) -> str:
        """在Pod中执行命令"""
        try:
            from kubernetes.stream import stream
            
            exec_command = list(command) if isinstance(command, list) else [command]
            
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
            dest_dir = os.path.dirname(local_path) or "."
            os.makedirs(dest_dir, exist_ok=True)
            abs_dest = os.path.realpath(dest_dir)
            with tarfile.open(fileobj=tar_data, mode='r:') as tar:
                for member in tar.getmembers():
                    member_path = os.path.realpath(os.path.join(abs_dest, member.name))
                    if not member_path.startswith(abs_dest + os.sep) and member_path != abs_dest:
                        raise ValueError(f"tar 成员路径越界: {member.name}")
                tar.extractall(path=dest_dir)
            return local_path

        await asyncio.to_thread(_do_copy)
        return local_path

    async def read_pod_files(
        self,
        pod_name: str,
        pod_paths: List[str],
        namespace: str = "default",
        container: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """从 Pod 读取文件内容到内存（不落盘），返回 [{path, content, encoding, size}]"""
        import tarfile
        import base64
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _read_one(pod_path: str) -> Dict[str, Any]:
            parent = os.path.dirname(pod_path) or "."
            base = os.path.basename(pod_path)
            cmd = ['tar', 'cf', '-', '-C', parent, base]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=False, stdout=True, tty=False,
                _preload_content=False,
                binary=True,
            )
            tar_data = BytesIO()
            while resp.is_open():
                resp.update(timeout=5)
                if resp.peek_stdout():
                    out = resp.read_stdout()
                    if isinstance(out, str):
                        out = out.encode('latin1')
                    tar_data.write(out)
            resp.close()
            tar_data.seek(0)

            results: list[dict] = []
            try:
                with tarfile.open(fileobj=tar_data, mode='r:') as tar:
                    for member in tar.getmembers():
                        if not member.isfile():
                            continue
                        f = tar.extractfile(member)
                        if f is None:
                            continue
                        raw = f.read()
                        if len(raw) > MAX_POD_FILE_SIZE:
                            results.append({
                                "path": os.path.join(os.path.dirname(pod_path), member.name),
                                "content": None,
                                "encoding": None,
                                "size": len(raw),
                                "error": f"文件过大 ({len(raw)} bytes)，超过 {MAX_POD_FILE_SIZE} 上限",
                            })
                            continue
                        try:
                            text = raw.decode("utf-8")
                            results.append({
                                "path": os.path.join(os.path.dirname(pod_path), member.name),
                                "content": text,
                                "encoding": "text",
                                "size": len(raw),
                            })
                        except UnicodeDecodeError:
                            results.append({
                                "path": os.path.join(os.path.dirname(pod_path), member.name),
                                "content": base64.b64encode(raw).decode("ascii"),
                                "encoding": "base64",
                                "size": len(raw),
                            })
            except tarfile.TarError as e:
                results.append({"path": pod_path, "error": f"tar 解析失败: {e}"})
            return results

        import os
        all_results = []
        for p in pod_paths:
            items = await asyncio.to_thread(_read_one, p)
            all_results.extend(items)
        return all_results

    async def write_pod_file(
        self,
        pod_name: str,
        pod_path: str,
        content: str,
        encoding: str = "text",
        namespace: str = "default",
        container: Optional[str] = None,
    ) -> str:
        """将内容写入 Pod 中的文件（不依赖本地磁盘）"""
        import os
        import tarfile
        import base64
        import asyncio
        from io import BytesIO
        from kubernetes.stream import stream

        def _do_write():
            if encoding == "base64":
                raw = base64.b64decode(content)
            else:
                raw = content.encode("utf-8")

            tar_buffer = BytesIO()
            filename = os.path.basename(pod_path)
            info = tarfile.TarInfo(name=filename)
            info.size = len(raw)
            with tarfile.open(fileobj=tar_buffer, mode='w') as tar:
                tar.addfile(info, BytesIO(raw))
            tar_buffer.seek(0)
            tar_bytes = tar_buffer.read()

            dest_dir = os.path.dirname(pod_path) or "/"
            cmd = ['tar', 'xf', '-', '-C', dest_dir]
            resp = stream(
                self.v1_api.connect_get_namespaced_pod_exec,
                pod_name, namespace,
                command=cmd,
                container=container,
                stderr=True, stdin=True, stdout=True, tty=False,
                _preload_content=False,
                binary=True,
            )
            chunk_size = 1024 * 64
            for i in range(0, len(tar_bytes), chunk_size):
                resp.write_stdin(tar_bytes[i:i + chunk_size])
            resp.close()
            return pod_path

        await asyncio.to_thread(_do_write)
        return pod_path

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
                          namespace: str = "default",
                          idle_timeout: int = 0) -> Dict[str, Any]:
        """Pod端口转发 - 在本地端口与Pod端口之间建立真实转发。

        返回值中包含 _run_flag 引用，调用方可通过设置
        _run_flag["running"] = False 来停止转发。
        """
        import threading
        import socket
        import select
        from kubernetes import client as k8s_client
        from kubernetes.stream import portforward

        # 创建独立的 CoreV1Api 用于端口转发。
        # portforward() 会临时 monkey-patch api_client.request，
        # 如果共享 self.v1_api 会导致并发请求（如 list_events）
        # 收到 "Missing required parameter 'ports'" 错误。
        pf_api_client = k8s_client.ApiClient(
            configuration=self.v1_api.api_client.configuration
        )
        pf_v1_api = k8s_client.CoreV1Api(api_client=pf_api_client)

        def _bridge_sockets(local_sock, remote_sock):
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
                for s in (local_sock, remote_sock):
                    try:
                        s.close()
                    except Exception:
                        pass

        def _handle_connection(client_socket):
            try:
                pf = portforward(
                    pf_v1_api.connect_get_namespaced_pod_portforward,
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

        import time as _time
        run_flag = {"running": True}
        server_ref: Dict[str, Any] = {}
        last_activity = {"ts": _time.monotonic()}

        def _handle_connection_wrapper(client_socket):
            last_activity["ts"] = _time.monotonic()
            _handle_connection(client_socket)
            last_activity["ts"] = _time.monotonic()

        def _run_forward_server():
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_ref["socket"] = server
            try:
                server.bind(("127.0.0.1", local_port))
                server.listen(5)
                server.settimeout(1.0)
                while run_flag["running"]:
                    if idle_timeout > 0:
                        idle_sec = _time.monotonic() - last_activity["ts"]
                        if idle_sec >= idle_timeout:
                            run_flag["running"] = False
                            break
                    try:
                        client_sock, _ = server.accept()
                        t = threading.Thread(target=_handle_connection_wrapper, args=(client_sock,), daemon=True)
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

        server_thread = threading.Thread(target=_run_forward_server, daemon=True)
        server_thread.start()

        return {
            "pod_name": pod_name,
            "namespace": namespace,
            "local_port": local_port,
            "pod_port": pod_port,
            "status": "running",
            "message": f"端口转发已启动: localhost:{local_port} -> {pod_name}:{pod_port}",
            "note": f"转发在后台运行，访问 http://127.0.0.1:{local_port} 可访问 Pod 服务。"
                    "可通过 port_forward(action='stop') 停止。",
            "_run_flag": run_flag,
            "_server_ref": server_ref,
        }

