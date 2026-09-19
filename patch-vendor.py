from pathlib import Path

replacements = {
    "setup/k3s.sh": {
        "sudo rc-service k3s start": "sudo systemctl start k3s",
        "sudo rc-update add k3s": "sudo systemctl enable k3s",
    },
    "setup/helper.sh": {
        "sudo rc-service k3s restart": "sudo systemctl restart k3s",
    },
    "setup/experimental_swap.sh": {
        "sudo rc-update add swap boot": "sudo systemctl daemon-reload || true",
        "sudo rc-service k3s stop": "sudo systemctl stop k3s",
        "sudo rc-service k3s restart": "sudo systemctl restart k3s",
        "echo 0 | sudo tee /sys/fs/cgroup/openrc.k3s/memory.swap.max": (
            "if [ -w /sys/fs/cgroup/system.slice/k3s.service/memory.swap.max ]; "
            "then echo 0 | sudo tee /sys/fs/cgroup/system.slice/k3s.service/memory.swap.max >/dev/null; fi"
        ),
    },
}

for relative_path, file_replacements in replacements.items():
    path = Path(relative_path)
    if not path.exists():
        print(f"skip missing {relative_path}")
        continue
    text = path.read_text()
    needed = any(old in text for old in file_replacements)
    if not needed:
        print(f"already patched {relative_path}; skipping")
        continue
    bak = Path(str(path) + ".ubuntu-patch.bak")
    if not bak.exists():
        bak.write_bytes(path.read_bytes())
    for old, new in file_replacements.items():
        text = text.replace(old, new)
    path.write_text(text)
    print(f"patched {relative_path}")
