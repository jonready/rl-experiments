FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

RUN apt-get update -qq && \
    apt-get install -y -qq tmux htop nvtop && \
    rm -rf /var/lib/apt/lists/*

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# prime-rl + deps
WORKDIR /opt/prime-rl
RUN git clone https://github.com/PrimeIntellect-ai/prime-rl.git . && \
    uv tool install prime && \
    uv sync --all-extras && \
    uv pip install wordle --extra-index-url https://hub.primeintellect.ai/will/simple/ && \
    uv pip install awscli
