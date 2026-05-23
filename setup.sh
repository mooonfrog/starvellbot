#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/mooonfrog/starvellbot.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
SB_USER="${SB_USER:-starvellbot}"
SB_HOME="${SB_HOME:-/opt/starvellbot}"
SERVICE_NAME="${SERVICE_NAME:-starvellbot}"
SETUP_URL="${SETUP_URL:-https://raw.githubusercontent.com/mooonfrog/starvellbot/${REPO_BRANCH}/setup.sh}"

SCRIPT_PATH="${BASH_SOURCE[0]:-$0}"
PIPED=0
if [ -z "$SCRIPT_PATH" ] || [ "$SCRIPT_PATH" = "bash" ] || [ "$SCRIPT_PATH" = "-bash" ] || [ ! -f "$SCRIPT_PATH" ]; then
    PIPED=1
fi

if [ -t 1 ]; then
    C_RESET=$'\033[0m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_RED=$'\033[31m'
    C_CYAN=$'\033[36m'
    C_MAGENTA=$'\033[35m'
    C_BOLD=$'\033[1m'
else
    C_RESET=""; C_GREEN=""; C_YELLOW=""; C_RED=""
    C_CYAN=""; C_MAGENTA=""; C_BOLD=""
fi

info() { printf "%s[+]%s %s\n" "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf "%s[!]%s %s\n" "$C_YELLOW" "$C_RESET" "$*"; }
fail() { printf "%s[x]%s %s\n" "$C_RED"    "$C_RESET" "$*" >&2; }
step() { printf "\n%s%s==>%s %s%s%s\n" "$C_BOLD" "$C_CYAN" "$C_RESET" "$C_BOLD" "$*" "$C_RESET"; }

banner() {
    printf "%s%s" "$C_MAGENTA" "$C_BOLD"
    cat <<'EOF'

   ┌─┐┌┬┐┌─┐┬─┐┬  ┬┌─┐┬  ┬  ┌┐ ┌─┐┌┬┐
   └─┐ │ ├─┤├┬┘└┐┌┘├┤ │  │  ├┴┐│ │ │ 
   └─┘ ┴ ┴ ┴┴└─ └┘ └─┘┴─┘┴─┘└─┘└─┘ ┴ 

   ʕっ•ᴥ•ʔっ  StarvellBot installer
EOF
    printf "%s\n\n" "$C_RESET"
}

need_cmd() { command -v "$1" >/dev/null 2>&1; }

require_linux() {
    if [ "$(uname -s)" != "Linux" ]; then
        fail "этот установщик только для Linux с systemd"
        exit 1
    fi
}

require_systemd() {
    if ! need_cmd systemctl || [ ! -d /run/systemd/system ]; then
        fail "systemd не найден. установщик заточен под systemd-дистрибутивы"
        exit 1
    fi
}

require_root() {
    if [ "$(id -u)" -eq 0 ]; then
        return 0
    fi
    if ! need_cmd sudo; then
        fail "нужны права root и нет sudo. запусти от root"
        exit 1
    fi
    warn "нет прав root, перезапускаю через sudo"
    local env_pass=(
        "REPO_URL=$REPO_URL"
        "REPO_BRANCH=$REPO_BRANCH"
        "SB_USER=$SB_USER"
        "SB_HOME=$SB_HOME"
        "SERVICE_NAME=$SERVICE_NAME"
        "SETUP_URL=$SETUP_URL"
    )
    if [ "$PIPED" = "1" ]; then
        if ! need_cmd curl; then
            fail "при запуске через пайп нужен curl для re-exec под sudo"
            exit 1
        fi
        exec sudo -E env "${env_pass[@]}" bash -c "curl -fsSL '$SETUP_URL' | bash"
    fi
    exec sudo -E env "${env_pass[@]}" bash "$SCRIPT_PATH" "$@"
}

find_python() {
    for cand in python3.12 python3.11 python3.10 python3; do
        if need_cmd "$cand"; then
            ver=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "0.0")
            major=${ver%%.*}
            minor=${ver##*.}
            if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 10 ]; }; then
                echo "$cand"
                return 0
            fi
        fi
    done
    return 1
}

install_system_deps() {
    step "системные зависимости"
    if need_cmd apt-get; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y
        apt-get install -y --no-install-recommends git ca-certificates python3 python3-venv python3-pip
    elif need_cmd dnf; then
        dnf install -y git ca-certificates python3 python3-virtualenv python3-pip
    elif need_cmd yum; then
        yum install -y git ca-certificates python3 python3-pip
    elif need_cmd pacman; then
        pacman -Sy --noconfirm git ca-certificates python python-pip
    elif need_cmd zypper; then
        zypper --non-interactive install git ca-certificates python3 python3-pip python3-venv
    elif need_cmd apk; then
        apk add --no-cache git ca-certificates python3 py3-pip
    else
        warn "пакетный менеджер не определён, надеюсь зависимости уже стоят"
    fi
}

create_user() {
    step "пользователь $SB_USER"
    if id "$SB_USER" >/dev/null 2>&1; then
        info "пользователь $SB_USER уже есть"
    else
        useradd --system --create-home --home-dir "$SB_HOME" --shell /bin/bash "$SB_USER"
        info "создан системный пользователь $SB_USER ($SB_HOME)"
    fi
    install -d -o "$SB_USER" -g "$SB_USER" -m 0750 "$SB_HOME"
}

clone_repo() {
    step "репозиторий"
    if [ -d "$SB_HOME/.git" ]; then
        info "репо уже есть, обновляю"
        sudo -u "$SB_USER" git -C "$SB_HOME" fetch --all --prune
        sudo -u "$SB_USER" git -C "$SB_HOME" checkout "$REPO_BRANCH"
        sudo -u "$SB_USER" git -C "$SB_HOME" pull --ff-only
    else
        if [ -n "$(ls -A "$SB_HOME" 2>/dev/null || true)" ]; then
            warn "$SB_HOME не пуст, попробую клонировать рядом и переместить"
            tmp_dir=$(mktemp -d)
            chown "$SB_USER:$SB_USER" "$tmp_dir"
            sudo -u "$SB_USER" git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$tmp_dir/repo"
            shopt -s dotglob
            mv "$tmp_dir/repo/"* "$SB_HOME/"
            shopt -u dotglob
            rm -rf "$tmp_dir"
            chown -R "$SB_USER:$SB_USER" "$SB_HOME"
        else
            sudo -u "$SB_USER" git clone --branch "$REPO_BRANCH" --single-branch "$REPO_URL" "$SB_HOME"
        fi
    fi
}

setup_venv() {
    step "виртуальное окружение"
    local py
    py=$(find_python) || { fail "не нашёл python 3.10+"; exit 1; }
    info "питон: $py ($("$py" --version 2>&1))"

    if [ ! -x "$SB_HOME/.venv/bin/python" ]; then
        sudo -u "$SB_USER" "$py" -m venv "$SB_HOME/.venv"
    else
        info "venv уже есть"
    fi

    info "обновляю pip и зависимости"
    sudo -u "$SB_USER" "$SB_HOME/.venv/bin/python" -m pip install --upgrade pip
    sudo -u "$SB_USER" "$SB_HOME/.venv/bin/python" -m pip install -r "$SB_HOME/requirements.txt"
}

run_first_time_setup() {
    step "первый запуск (визард настройки)"
    info "сейчас откроется опросник. заполни session cookie, tg-токен и пароль"
    info "после успешной настройки заверши процесс через Ctrl+C — потом подниму как сервис"
    sleep 1

    if [ ! -t 0 ] && [ -r /dev/tty ]; then
        exec < /dev/tty
    fi

    set +e
    sudo -u "$SB_USER" -H bash -c "cd '$SB_HOME' && '.venv/bin/python' app.py"
    local rc=$?
    set -e

    if [ ! -f "$SB_HOME/configs/_main.cfg" ] || [ ! -f "$SB_HOME/configs/_tg.cfg" ]; then
        fail "конфиги не созданы. визард не дошёл до конца"
        exit 1
    fi
    info "первичная настройка завершена (код выхода $rc)"
}

write_service() {
    step "systemd-сервис $SERVICE_NAME"
    local unit="/etc/systemd/system/${SERVICE_NAME}.service"
    cat > "$unit" <<EOF
[Unit]
Description=StarvellBot - bot for starvell.com
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SB_USER
Group=$SB_USER
WorkingDirectory=$SB_HOME
ExecStart=$SB_HOME/.venv/bin/python $SB_HOME/app.py
Restart=on-failure
RestartSec=5
KillMode=mixed
TimeoutStopSec=15
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$SB_HOME

[Install]
WantedBy=multi-user.target
EOF
    info "юнит записан в $unit"
}

start_service() {
    step "запуск сервиса"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        info "сервис $SERVICE_NAME запущен"
    else
        fail "сервис не поднялся, смотри логи: journalctl -u $SERVICE_NAME -n 100"
        exit 1
    fi
}

print_summary() {
    step "готово"
    cat <<EOF
${C_GREEN}StarvellBot установлен.${C_RESET}

  каталог:        $SB_HOME
  пользователь:   $SB_USER
  сервис:         $SERVICE_NAME

  статус:         systemctl status $SERVICE_NAME
  логи:           journalctl -u $SERVICE_NAME -f
  перезапуск:     systemctl restart $SERVICE_NAME
  остановить:     systemctl stop $SERVICE_NAME
  выключить:      systemctl disable $SERVICE_NAME

EOF
}

main() {
    banner
    require_linux
    require_systemd
    require_root "$@"
    install_system_deps
    create_user
    clone_repo
    setup_venv
    run_first_time_setup
    write_service
    start_service
    print_summary
}

main "$@"
