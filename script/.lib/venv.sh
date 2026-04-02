#!/bin/bash

# shellcheck shell=bash

activate_ha_venv() {
    local workspace_venv="$PWD/.local/ha-venv"
    local home_venv="$HOME/.local/ha-venv"
    local target_venv=""

    if [[ -f "$workspace_venv/bin/activate" ]]; then
        target_venv="$workspace_venv"
    elif [[ -f "$home_venv/bin/activate" ]]; then
        target_venv="$home_venv"
    else
        log_error "Virtual environment not found in $workspace_venv or $home_venv"
        exit 1
    fi

    local target_real
    target_real="$(cd "$target_venv" && pwd -P)"

    local current_real=""
    if [[ -n ${VIRTUAL_ENV:-} ]] && [[ -d ${VIRTUAL_ENV:-} ]]; then
        current_real="$(cd "$VIRTUAL_ENV" && pwd -P)"
    fi

    if [[ "$current_real" == "$target_real" ]]; then
        return
    fi

    log_header "Activating virtual environment"
    # shellcheck source=/dev/null
    source "$target_venv/bin/activate"
}
