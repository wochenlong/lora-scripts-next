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

echo "Installing deps..."

cd "$script_dir" || exit
pip install --upgrade -r requirements.txt

echo "Install completed"
echo ""
echo "Note: training dependencies (torch, sd-scripts stack) are no longer part of"
echo "this environment. Install training engines from the UI: Settings -> Training Engines."
