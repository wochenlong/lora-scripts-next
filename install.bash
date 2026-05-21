#!/usr/bin/bash

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
create_venv=true

while [ -n "$1" ]; do
    case "$1" in
        --disable-venv)
            create_venv=false
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Ensure the pinned vendor/sd-scripts submodule (Anima training engine) is
# present. Safe to run repeatedly; skips silently when not a git checkout.
if [ -d "$script_dir/.git" ] || [ -f "$script_dir/.git" ]; then
    echo "Syncing git submodules (vendor/sd-scripts)..."
    git -C "$script_dir" submodule update --init --recursive || \
        echo "Warning: submodule init failed; Anima training may not start. Run 'git submodule update --init --recursive' manually."
fi

if $create_venv; then
    echo "Creating python venv..."
    python3 -m venv venv
    source "$script_dir/venv/bin/activate"
    echo "active venv"
fi

echo "Installing torch & xformers..."

cuda_version=$(nvidia-smi | grep -oiP 'CUDA Version: \K[\d\.]+')

if [ -z "$cuda_version" ]; then
    cuda_version=$(nvcc --version | grep -oiP 'release \K[\d\.]+')
fi
cuda_major_version=$(echo "$cuda_version" | awk -F'.' '{print $1}')
cuda_minor_version=$(echo "$cuda_version" | awk -F'.' '{print $2}')

echo "CUDA Version: $cuda_version"


if (( cuda_major_version >= 12 )); then
    echo "install torch 2.7.0+cu128"
    pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --extra-index-url https://download.pytorch.org/whl/cu128
    pip install --no-deps xformers==0.0.30 --extra-index-url https://download.pytorch.org/whl/cu128
elif (( cuda_major_version == 11 && cuda_minor_version >= 8 )); then
    echo "install torch 2.4.0+cu118"
    pip install torch==2.4.0+cu118 torchvision==0.19.0+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
    pip install --no-deps xformers==0.0.27.post2+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
elif (( cuda_major_version == 11 && cuda_minor_version >= 6 )); then
    echo "install torch 1.12.1+cu116"
    pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
    # for RTX3090+cu113/cu116 xformers, we need to install this version from source. You can also try xformers==0.0.18
    pip install --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
    pip install triton==2.0.0.dev20221202
elif (( cuda_major_version == 11 && cuda_minor_version >= 2 )); then
    echo "install torch 1.12.1+cu113"
    pip install torch==1.12.1+cu113 torchvision==0.13.1+cu113 --extra-index-url https://download.pytorch.org/whl/cu116
    pip install --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
    pip install triton==2.0.0.dev20221202
else
    echo "Unsupported cuda version:$cuda_version"
    exit 1
fi

echo "Installing deps..."

cd "$script_dir" || exit
pip install --upgrade -r requirements.txt

echo "Installing Flash Attention 2 (optional, for training acceleration)..."
export MAX_JOBS="${MAX_JOBS:-4}"
if pip install "flash-attn==2.7.4.post1" --no-build-isolation; then
    if python -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary" 2>/dev/null; then
        echo "Flash Attention 2 installed and verified successfully"
    else
        echo "Flash Attention 2 self-check failed (non-fatal, will use xformers or PyTorch SDPA)"
        pip uninstall flash-attn flash_attn triton -y >/dev/null 2>&1 || true
    fi
else
    echo "Flash Attention 2 install failed (non-fatal, will use xformers or PyTorch SDPA)"
fi

echo "Install completed"
