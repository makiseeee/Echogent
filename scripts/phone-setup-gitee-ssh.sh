#!/usr/bin/env bash
set -euo pipefail

KEY="$HOME/.ssh/id_ed25519_gitee"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"

if [[ ! -f "$KEY" ]]; then
  ssh-keygen -t ed25519 -N "" -C "echo-phone-gitee-$(date +%F)" -f "$KEY"
fi

cat >"$HOME/.ssh/config" <<'EOF'
Host gitee.com
    HostName gitee.com
    User git
    IdentityFile ~/.ssh/id_ed25519_gitee
    IdentitiesOnly yes
EOF
chmod 600 "$HOME/.ssh/config" "$KEY"
chmod 644 "$KEY.pub"
cat "$KEY.pub"
