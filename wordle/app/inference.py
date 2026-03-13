"""Manages the inference server on the devbox via SSH (paramiko)."""

import os
import time

import paramiko


class DevboxInference:
    def __init__(self):
        self.host = os.environ.get("DEVBOX_HOST", "box")
        self.user = os.environ.get("DEVBOX_USER", "jonathonready")
        self.key_path = os.path.expanduser(
            os.environ.get("DEVBOX_KEY_PATH", "~/.ssh/id_ed25519")
        )
        self.r2_endpoint = "https://0bbaac9c9052f0808f4187461bdefbfc.r2.cloudflarestorage.com"
        self.r2_bucket = "primeintellectmodels"
        self.r2_access_key = os.environ["R2_PRIMEINT_ACCESSKEYID"]
        self.r2_secret_key = os.environ["R2_PRIMEINT_SECRETACCESSKEY"]
        self.model_dir = "~/wordle-models"
        self.current_step = None
        self._client = None

    def _connect(self) -> paramiko.SSHClient:
        if self._client and self._client.get_transport() and self._client.get_transport().is_active():
            return self._client
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            username=self.user,
            key_filename=self.key_path,
        )
        self._client = client
        return client

    def _run(self, cmd: str, timeout: int = 300) -> str:
        client = self._connect()
        _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode()
        err = stderr.read().decode()
        if exit_code != 0:
            raise RuntimeError(f"Command failed ({exit_code}): {cmd}\n{err}")
        return out

    def _configure_aws(self):
        """Ensure AWS CLI is configured on devbox for R2 access."""
        self._run(f"""mkdir -p ~/.aws && cat > ~/.aws/credentials <<'AWSEOF'
[default]
aws_access_key_id = {self.r2_access_key}
aws_secret_access_key = {self.r2_secret_key}
AWSEOF
cat > ~/.aws/config <<'AWSEOF'
[default]
region = auto
AWSEOF""")

    def download_checkpoint(self, step: str) -> str:
        """Download a checkpoint from R2 to the devbox. Returns model path."""
        self._configure_aws()
        model_path = f"{self.model_dir}/{step}"
        self._run(f"mkdir -p {model_path}")
        self._run(
            f"aws s3 sync s3://{self.r2_bucket}/wordle/rl/{step}/ {model_path}/ "
            f"--endpoint-url {self.r2_endpoint}",
            timeout=600,
        )
        return model_path

    def download_sft(self) -> str:
        """Download the SFT base model."""
        self._configure_aws()
        model_path = f"{self.model_dir}/sft_final"
        self._run(f"mkdir -p {model_path}")
        self._run(
            f"aws s3 sync s3://{self.r2_bucket}/wordle/sft/final/ {model_path}/ "
            f"--endpoint-url {self.r2_endpoint}",
            timeout=600,
        )
        return model_path

    def kill_server(self):
        """Kill any existing inference server."""
        try:
            self._run("pkill -f 'vllm.entrypoints' || true")
            time.sleep(2)
        except Exception:
            pass

    def start_server(self, model_path: str):
        """Start vLLM inference server on devbox."""
        self.kill_server()
        # Start in background via nohup
        cmd = (
            f"nohup python -m vllm.entrypoints.openai.api_server "
            f"--model {model_path} "
            f"--port 8000 "
            f"--max-model-len 2048 "
            f"> ~/vllm_server.log 2>&1 &"
        )
        self._run(cmd)

    def wait_for_ready(self, timeout: int = 120) -> bool:
        """Poll until the inference server is responsive."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                result = self._run("curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/v1/models")
                if result.strip() == "200":
                    return True
            except Exception:
                pass
            time.sleep(3)
        return False

    def switch_checkpoint(self, step: str) -> dict:
        """Full pipeline: download checkpoint, start server, wait for ready."""
        if step == "sft":
            model_path = self.download_sft()
        else:
            model_path = self.download_checkpoint(step)
        self.start_server(model_path)
        ready = self.wait_for_ready()
        if ready:
            self.current_step = step
        return {"ready": ready, "step": step, "model_path": model_path}

    def get_status(self) -> dict:
        """Check if server is running and which model is loaded."""
        try:
            result = self._run("curl -s http://localhost:8000/v1/models")
            running = True
        except Exception:
            running = False
            result = ""
        return {
            "running": running,
            "current_step": self.current_step,
            "response": result,
        }

    def close(self):
        if self._client:
            self._client.close()
            self._client = None
