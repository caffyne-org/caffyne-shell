#!/usr/bin/env bash
# =============================================================================
#  Caffyne Shell — Installer & Updater
#  Arch Linux only
# =============================================================================

set -euo pipefail

REPO_URL="https://github.com/caffyne-org/caffyne-shell.git"
INSTALL_DIR="$HOME/.config/caffyne-shell"
CONFIG_DIR="$INSTALL_DIR/config"
SCRIPT_URL="https://raw.githubusercontent.com/caffyne-org/caffyne-shell/main/install.sh"

# Directories to preserve during updates (relative to INSTALL_DIR)
PRESERVE_DIRS=("wallpapers")

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}${BOLD}[caffyne]${RESET} $*"; }
success() { echo -e "${GREEN}${BOLD}[  ok  ]${RESET} $*"; }
warn()    { echo -e "${YELLOW}${BOLD}[ warn ]${RESET} $*"; }
error()   { echo -e "${RED}${BOLD}[ err  ]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }

cat << "EOF"
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%%%@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@%*------*%@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@%=-----**-----=%@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%#=----=#@@@@@@#=-----#%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@%*-----+%@@@@#==#%@@@%+-----+%@@@@@@@@@@@@@@@
@@@@@@@@@@@%#=----=*@@@@%*--------*%@@@@*=----=#%@@@@@@@@@@@
@@@@@@@@@%+----+#@@@@#+--------------=#@@@@%+----=%@@@@@@@@@
@@@@@@@@@#---%@@@%#=---------------------#%@@@%---#@@@@@@@@@
@@@@@@@@@#--=@@%*--------------------------*%@@=-+%@@@@@@@@@
@@@@@@@@@#--=@@@@@%#=------------------=*%@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@%+------------+%@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@%*=----=*%@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@@@@@##@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@#--=@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%@@@@@@@@@
@@@@@@@@@#--=%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%*--#@@@@@@@@@
@@@@@@@@@%+----+%@@@@@@@@@@@@@@@@@@@@@@@@@@%+----=%@@@@@@@@@
@@@@@@@@@@@%#=----=*@@@@@@@@@@@@@@@@@@@@#=----=#%@@@@@@@@@@@
@@@@@@@@@@@@@@@%+-----+%@@@@@@@@@@@@%+-----+%@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@%#-----=#@@@@@@#=-----#%@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@%=-----**=----=#@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@%*------*%@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@%%%%@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
EOF

self_update() {
    local script_path
    script_path="$(realpath "$0")"

    info "Checking for installer updates..."

    local tmp_script
    tmp_script=$(mktemp)

    if ! curl -fsSL "$SCRIPT_URL" -o "$tmp_script" 2>/dev/null; then
        warn "Could not reach update URL — skipping self-update."
        rm -f "$tmp_script"
        return
    fi

    if cmp -s "$script_path" "$tmp_script"; then
        success "Installer is already up to date."
        rm -f "$tmp_script"
        return
    fi

    info "New version of install.sh found — updating..."
    chmod +x "$tmp_script"
    cp "$tmp_script" "$script_path"
    rm -f "$tmp_script"
    success "Installer updated. Re-running..."
    echo
    exec "$script_path" "$@"
}

# ── Sanity checks ─────────────────────────────────────────────────────────────
check_arch() {
    if ! command -v pacman &>/dev/null; then
        die "This installer is for Arch Linux only."
    fi
}

check_not_root() {
    if [[ "$EUID" -eq 0 ]]; then
        die "Please run this script as a regular user, not root."
    fi
}

# ── yay bootstrap ─────────────────────────────────────────────────────────────
ensure_yay() {
    if command -v yay &>/dev/null; then
        success "yay is already installed."
        return
    fi

    info "yay not found — installing from AUR..."
    sudo pacman -S --needed --noconfirm git base-devel

    local tmp
    tmp=$(mktemp -d)
    git clone https://aur.archlinux.org/yay.git "$tmp/yay"
    (cd "$tmp/yay" && makepkg -si --noconfirm)
    rm -rf "$tmp"
    success "yay installed."
}

# ── System dependencies ───────────────────────────────────────────────────────
install_pacman_deps() {
    info "Installing pacman dependencies..."

    local pacman_pkgs=(
        # GTK / GObject stack
        gtk3
        cairo
        libgirepository
        gobject-introspection
        gtk-layer-shell
        libdbusmenu-gtk3
        cinnamon-desktop
        gnome-bluetooth-3.0

        # Theming
        matugen

        # Media / hardware
        playerctl
        brightnessctl
        wf-recorder
        upower

        # Networking / Bluetooth
        networkmanager
        bluez

        # Python
        python
        python-pip

        # Wayland wallpaper daemon
        awww

        # Build tools (needed for compiling snippets)
        base-devel
        git
    )

    sudo pacman -S --needed --noconfirm "${pacman_pkgs[@]}"
    success "pacman dependencies installed."
}

install_aur_deps() {
    info "Installing AUR dependencies..."

    local aur_pkgs=(
        fabric-cli-git
        # gray-git we dont use no more
    )

    yay -S --needed --noconfirm "${aur_pkgs[@]}"
    success "AUR dependencies installed."
}

# ── Clone ─────────────────────────────────────────────────────────────────────
clone_repo() {
    info "Cloning Caffyne Shell to $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    success "Repository cloned."
}

# ── Python venv ───────────────────────────────────────────────────────────────
setup_venv() {
    info "Setting up Python virtual environment..."
    python -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
    success "Python dependencies installed."
}

# ── Compile native snippets ───────────────────────────────────────────────────
compile_snippets() {
    info "Compiling native libraries..."

    local blur_dir="$INSTALL_DIR/snippets/blur/lib"
    local hacktk_dir="$INSTALL_DIR/snippets/hacktk/lib"

    if [[ -d "$blur_dir" ]]; then
        make -C "$blur_dir"
        success "blur library compiled."
    else
        warn "blur lib directory not found — skipping."
    fi

    if [[ -d "$hacktk_dir" ]]; then
        make -C "$hacktk_dir"
        success "hacktk library compiled."
    else
        warn "hacktk directory not found — skipping."
    fi
}

inject_niri_include() {
    local niri_config="$HOME/.config/niri/config.kdl"
    local include_line='include "~/.config/caffyne-shell/config/niri.kdl"'

    if [[ ! -f "$niri_config" ]]; then
        info "No niri config found at $niri_config — skipping include injection."
        return
    fi

    if grep -qF "$include_line" "$niri_config"; then
        info "Niri include already present — skipping."
        return
    fi

    info "Appending caffyne include to niri config..."
    echo "" >> "$niri_config"
    echo "$include_line" >> "$niri_config"
    success "Niri config updated."
}

# ── Matugen Setup ─────────────────────────────────────────────────────────────
setup_matugen() {
    info "Configuring Matugen templates..."
    
    local matugen_config_dir="$HOME/.config/matugen"
    local matugen_conf="$matugen_config_dir/config.toml"
    local target_template="$matugen_config_dir/caffyne-shell-colors.css"
    local source_template="$INSTALL_DIR/matugen/caffyne-shell-colors.css"

    mkdir -p "$matugen_config_dir"

    if [[ ! -f "$matugen_conf" ]]; then
        info "Creating Matugen config.toml..."
        touch "$matugen_conf"
    fi

    if ! grep -q "^\[config\]$" "$matugen_conf"; then
        info "Adding [config] section..."
        printf "[config]\n" >> "$matugen_conf"
    fi
    
    if grep -q "\[templates.caffyne\]" "$matugen_conf"; then
        info "Matugen config entry already exists — skipping append."
    else
        info "Appending Caffyne template config to matugen/config.toml..."
        cat <<EOF >> "$matugen_conf"

# Caffyne Shell Colors
[templates.caffyne]
input_path = '~/.config/caffyne-shell/matugen/caffyne-shell-colors.css'
output_path = '~/.config/caffyne-shell/style/colors.css'
EOF
    fi
}

# ── Update ────────────────────────────────────────────────────────────────────
backup_preserved_dirs() {
    local tmp_backup="$1"
    for dir in "${PRESERVE_DIRS[@]}"; do
        local src="$INSTALL_DIR/$dir"
        if [[ -d "$src" ]]; then
            info "Preserving $dir/..."
            cp -r "$src" "$tmp_backup/$dir"
        fi
    done
}

restore_preserved_dirs() {
    local tmp_backup="$1"
    for dir in "${PRESERVE_DIRS[@]}"; do
        local backed_up="$tmp_backup/$dir"
        if [[ -d "$backed_up" ]]; then
            info "Restoring $dir/..."
            rm -rf "$INSTALL_DIR/$dir"
            cp -r "$backed_up" "$INSTALL_DIR/$dir"
        fi
    done
}

do_update() {
    info "Updating Caffyne Shell..."

    local tmp_backup
    tmp_backup=$(mktemp -d)

    backup_preserved_dirs "$tmp_backup"

    git -C "$INSTALL_DIR" fetch origin
    git -C "$INSTALL_DIR" reset --hard origin/main

    restore_preserved_dirs "$tmp_backup"
    rm -rf "$tmp_backup"

    info "Refreshing Python dependencies..."
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q
    success "Python dependencies updated."

    compile_snippets

    success "Caffyne Shell updated successfully!"
    echo
    info "Restart the shell to apply changes."
}

# ── Fresh install ─────────────────────────────────────────────────────────────
do_install() {
    info "Starting fresh install of Caffyne Shell..."

    ensure_yay
    install_pacman_deps
    install_aur_deps
    clone_repo
    setup_venv
    
    compile_snippets
    inject_niri_include
    setup_matugen

    echo
    success "Caffyne Shell installed successfully!"
    echo
    echo -e "  ${BOLD}Start it:${RESET}"
    echo -e "    ${CYAN}~/.config/caffyne-shell/start.sh${RESET}"
    echo
    echo -e "  ${BOLD}Compositor configs live in:${RESET}"
    echo -e "    ${CYAN}~/.config/caffyne-shell/config/${RESET}"
    echo
}

# ── Entry point ───────────────────────────────────────────────────────────────
main() {
    echo
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║       Caffyne Shell Setup        ║${RESET}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════╝${RESET}"
    echo

    check_arch
    check_not_root
    self_update "$@"

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        warn "Existing installation found at $INSTALL_DIR"
        echo
        echo -e "  ${BOLD}1)${RESET} Update (preserves wallpapers/)"
        echo -e "  ${BOLD}2)${RESET} Reinstall from scratch (wipes everything)"
        echo -e "  ${BOLD}q)${RESET} Quit"
        echo
        read -rp "  Choice [1/2/q]: " choice
        case "$choice" in
            1) do_update ;;
            2)
                warn "Removing existing installation..."
                rm -rf "$INSTALL_DIR"
                do_install
                ;;
            q|Q) info "Aborted."; exit 0 ;;
            *) die "Invalid choice." ;;
        esac
    else
        do_install
    fi
}

main "$@"
