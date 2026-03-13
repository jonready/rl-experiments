"""GPU spot lifecycle: scan, launch, resume, destroy, setup-registry. RunPod primary, Verda fallback."""

import argparse
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

STATE_FILE = os.path.join(os.path.dirname(__file__), ".pod_state.json")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_NAME = "ghcr.io/jonready/rl-experiments:latest"


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_state() -> dict | None:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None


# --- RunPod ---


def runpod_scan():
    import runpod

    runpod.api_key = os.environ["RUNPOD_KEY"]
    gpus = runpod.get_gpus()

    print(f"\n{'GPU Type':<35} {'VRAM':<8} {'Spot $/hr':<12} {'On-demand':<12}")
    print("-" * 75)

    detailed = []
    for gpu in gpus:
        gpu_id = gpu.get("id", "?")
        try:
            detail = runpod.get_gpu(gpu_id)
            detailed.append(detail)
        except Exception:
            detailed.append(gpu)

    for gpu in sorted(detailed, key=lambda g: g.get("communitySpotPrice") or 999):
        name = gpu.get("id", "?")
        vram = gpu.get("memoryInGb", "?")
        spot = gpu.get("communitySpotPrice")
        ondemand = gpu.get("communityPrice")
        spot_str = f"${spot:.2f}" if spot else "N/A"
        ondemand_str = f"${ondemand:.2f}" if ondemand else "N/A"
        print(f"{name:<35} {vram:<8} {spot_str:<12} {ondemand_str:<12}")


def runpod_setup_registry():
    """One-time setup: register GHCR credentials with RunPod."""
    import runpod

    runpod.api_key = os.environ["RUNPOD_KEY"]

    ghcr_pat = os.environ.get("GHCR_PAT")
    if not ghcr_pat:
        print("Set GHCR_PAT env var to a GitHub Personal Access Token with packages:read scope.")
        print("Generate one at: https://github.com/settings/tokens/new?scopes=read:packages")
        sys.exit(1)

    print("Registering GHCR credentials with RunPod...")
    runpod.create_container_registry_auth(
        name="ghcr",
        username="jonready",
        password=ghcr_pat,
    )
    print("Done. RunPod can now pull from ghcr.io/jonready/*")


def runpod_launch(gpu_type: str, gpu_count: int, resume: bool = False):
    import runpod
    from runpod.api.graphql import run_graphql_query

    runpod.api_key = os.environ["RUNPOD_KEY"]

    r2_endpoint = "https://0bbaac9c9052f0808f4187461bdefbfc.r2.cloudflarestorage.com"
    r2_bucket = "primeintellectmodels"

    env_vars = {
        "R2_ENDPOINT": r2_endpoint,
        "R2_ACCESS_KEY": os.environ["R2_PRIMEINT_ACCESSKEYID"],
        "R2_SECRET_KEY": os.environ["R2_PRIMEINT_SECRETACCESSKEY"],
        "R2_BUCKET": r2_bucket,
        "RESUME": "1" if resume else "0",
    }

    # Get spot price for bid
    gpu_detail = runpod.get_gpu(gpu_type)
    spot_price = gpu_detail.get("communitySpotPrice") or gpu_detail.get("secureSpotPrice")
    if not spot_price:
        print(f"No spot pricing available for {gpu_type}, falling back to on-demand.")
        spot_price = gpu_detail.get("communityPrice", 0.5)

    env_items = ", ".join(f'{{ key: "{k}", value: "{v}" }}' for k, v in env_vars.items())

    print(f"Creating RunPod spot pod: {gpu_count}x {gpu_type} @ ${spot_price:.2f}/gpu/hr...")
    print(f"Image: {IMAGE_NAME}")
    mutation = f"""
    mutation {{
      podRentInterruptable(
        input: {{
          bidPerGpu: {spot_price}
          cloudType: ALL
          gpuCount: {gpu_count}
          volumeInGb: 50
          containerDiskInGb: 50
          minVcpuCount: 2
          minMemoryInGb: 15
          gpuTypeId: "{gpu_type}"
          name: "rl-training"
          imageName: "{IMAGE_NAME}"
          dockerArgs: ""
          startSsh: true
          ports: "22/tcp"
          volumeMountPath: "/workspace"
          env: [{env_items}]
        }}
      ) {{
        id
        imageName
        env
        machineId
        machine {{
          podHostId
        }}
      }}
    }}
    """
    raw_response = run_graphql_query(mutation)
    pod = raw_response["data"]["podRentInterruptable"]

    pod_id = pod["id"]
    print(f"Pod created: {pod_id}")
    save_state({"provider": "runpod", "pod_id": pod_id, "gpu_type": gpu_type, "gpu_count": gpu_count})

    # Wait for pod to be running
    print("Waiting for pod to start...")
    for _ in range(60):
        status = runpod.get_pod(pod_id)
        state = status.get("desiredStatus", "")
        runtime = status.get("runtime", {})
        if runtime and runtime.get("uptimeInSeconds", 0) > 0:
            print(f"Pod is RUNNING (uptime: {runtime['uptimeInSeconds']}s)")
            break
        print(f"  Status: {state}...")
        time.sleep(10)
    else:
        print("Timed out waiting for pod to start. Check RunPod dashboard.")
        return

    # Get SSH details
    ports = runtime.get("ports", [])
    ssh_port = None
    ssh_host = None
    for p in ports:
        if p.get("privatePort") == 22:
            ssh_host = p.get("ip")
            ssh_port = p.get("publicPort")
            break

    if ssh_host and ssh_port:
        print(f"\nSSH: ssh root@{ssh_host} -p {ssh_port}")
        save_state({
            "provider": "runpod",
            "pod_id": pod_id,
            "ssh_host": ssh_host,
            "ssh_port": ssh_port,
            "gpu_type": gpu_type,
            "gpu_count": gpu_count,
        })

        # SCP training scripts and configs, then start training
        print("\nUploading training scripts...")
        wordle_dir = os.path.join(SCRIPT_DIR, "wordle")
        scp_base = f"scp -P {ssh_port}"
        os.system(f"{scp_base} {wordle_dir}/train_remote.sh root@{ssh_host}:~/train_remote.sh")
        os.system(f"{scp_base} {wordle_dir}/sync_checkpoints.sh root@{ssh_host}:~/sync_checkpoints.sh")
        os.system(f"{scp_base} -r {wordle_dir}/configs root@{ssh_host}:~/configs")
        os.system(f"ssh -p {ssh_port} root@{ssh_host} 'chmod +x ~/train_remote.sh ~/sync_checkpoints.sh'")

        print("\nStarting training in tmux session...")
        env_str = " ".join(f"{k}={v}" for k, v in env_vars.items())
        os.system(
            f"ssh -p {ssh_port} root@{ssh_host} "
            f"'tmux new-session -d -s training \"{env_str} bash ~/train_remote.sh\"'"
        )
        print("Training started! Monitor with:")
        print(f"  ssh -p {ssh_port} root@{ssh_host} 'tmux attach -t training'")
    else:
        print("Could not find SSH connection details. Check RunPod dashboard.")


def runpod_destroy():
    import runpod

    runpod.api_key = os.environ["RUNPOD_KEY"]
    state = load_state()
    if not state or state.get("provider") != "runpod":
        print("No RunPod pod state found.")
        return
    pod_id = state["pod_id"]
    print(f"Destroying pod {pod_id}...")
    runpod.terminate_pod(pod_id)
    os.remove(STATE_FILE)
    print("Pod destroyed.")


# --- Verda ---


def verda_scan():
    try:
        from verda import VerdaClient

        client = VerdaClient(
            os.environ["VERDA_CLIENT_ID"],
            os.environ["VERDA_CLIENT_SECRET"],
        )
        availabilities = client.instances.get_availabilities(is_spot=True)
        print(f"\n{'Location':<12} {'Available Spot Instance Types'}")
        print("-" * 70)
        for loc in availabilities:
            code = loc.get("location_code", "?")
            types = loc.get("availabilities", [])
            gpu_types = [t for t in types if not t.startswith("CPU")]
            if gpu_types:
                print(f"{code:<12} {', '.join(gpu_types)}")
    except Exception as e:
        print(f"Verda scan failed: {e}")


def verda_launch(gpu_type: str, gpu_count: int, resume: bool = False):
    from verda import VerdaClient

    client = VerdaClient(
        os.environ["VERDA_CLIENT_ID"],
        os.environ["VERDA_CLIENT_SECRET"],
    )

    print(f"Creating Verda spot instance: {gpu_type}...")
    instance = client.instances.create(
        instance_type=gpu_type,
        image="ubuntu-24.04-cuda-12.8-open-docker",
        hostname="rl-training",
        description="RL training",
        is_spot=True,
    )
    instance_id = instance.id
    print(f"Instance created: {instance_id}")
    save_state({"provider": "verda", "instance_id": instance_id, "gpu_type": gpu_type, "gpu_count": gpu_count})

    ip = getattr(instance, "ip", None)
    if ip:
        print(f"SSH: ssh root@{ip}")
    else:
        print("Check Verda dashboard for SSH details, then manually run train_remote.sh")


def verda_destroy():
    from verda import VerdaClient

    state = load_state()
    if not state or state.get("provider") != "verda":
        print("No Verda instance state found.")
        return
    client = VerdaClient(
        os.environ["VERDA_CLIENT_ID"],
        os.environ["VERDA_CLIENT_SECRET"],
    )
    instance_id = state["instance_id"]
    print(f"Destroying instance {instance_id}...")
    client.instances.action(instance_id, "delete", delete_permanently=True)
    os.remove(STATE_FILE)
    print("Instance destroyed.")


# --- CLI ---


def main():
    parser = argparse.ArgumentParser(description="GPU spot provisioning for RL training")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("scan", help="Show available spot GPUs")

    launch_p = sub.add_parser("launch", help="Launch a spot instance")
    launch_p.add_argument("--provider", choices=["runpod", "verda"], default="runpod")
    launch_p.add_argument("--gpu-type", default="NVIDIA GeForce RTX 3090")
    launch_p.add_argument("--gpu-count", type=int, default=2)

    sub.add_parser("resume", help="Re-provision and resume from latest checkpoint")

    sub.add_parser("destroy", help="Tear down the current pod/instance")

    sub.add_parser("setup-registry", help="One-time: register GHCR credentials with RunPod")

    args = parser.parse_args()

    if args.command == "scan":
        print("=== RunPod Spot GPUs ===")
        runpod_scan()
        print("\n=== Verda Spot GPUs ===")
        verda_scan()

    elif args.command == "launch":
        if args.provider == "runpod":
            runpod_launch(args.gpu_type, args.gpu_count)
        else:
            verda_launch(args.gpu_type, args.gpu_count)

    elif args.command == "resume":
        state = load_state()
        provider = "runpod"
        gpu_type = "NVIDIA GeForce RTX 3090"
        gpu_count = 2
        if state:
            provider = state.get("provider", "runpod")
            gpu_type = state.get("gpu_type", gpu_type)
            gpu_count = state.get("gpu_count", gpu_count)
        print(f"Resuming on {provider} with {gpu_count}x {gpu_type}...")
        if provider == "runpod":
            runpod_launch(gpu_type, gpu_count, resume=True)
        else:
            verda_launch(gpu_type, gpu_count, resume=True)

    elif args.command == "destroy":
        state = load_state()
        if not state:
            print("No active pod/instance found.")
            return
        if state["provider"] == "runpod":
            runpod_destroy()
        else:
            verda_destroy()

    elif args.command == "setup-registry":
        runpod_setup_registry()


if __name__ == "__main__":
    main()
