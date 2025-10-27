#!/bin/bash

PACKAGES="wget unzip cabextract zenity xdg-utils desktop-file-utils"

install_dependencies() {
    if command -v pacman &> /dev/null; then
        echo "Detected: Arch-based system (pacman)"
        echo "Installing packages: $PACKAGES"
        sudo pacman -S --noconfirm $PACKAGES
    
    elif command -v apt &> /dev/null; then
        echo "Detected: Debian/Ubuntu-based system (apt)"
        echo "Updating package lists..."
        sudo apt update
        echo "Installing packages: $PACKAGES"
        sudo apt install -y $PACKAGES

    elif command -v dnf &> /dev/null; then
        echo "Detected: Fedora/RHEL-based system (dnf)"
        echo "Installing packages: $PACKAGES"
        sudo dnf install -y $PACKAGES
    
    elif command -v zypper &> /dev/null; then
        echo "Detected: openSUSE-based system (zypper)"
        echo "Installing packages: $PACKAGES"
        sudo zypper install -y $PACKAGES

    else
        echo "Error: Could not determine the package manager (pacman, apt, dnf, or zypper not found)."
        echo "Please install the following packages manually: $PACKAGES"
        return 1
    fi

    if [ $? -eq 0 ]; then
        echo "---"
        echo "Success: All dependencies have been installed."
        return 0
    else
        echo "---"
        echo "Error: Dependency installation failed."
        return 1
    fi
}

echo "Starting dependency installation script..."
install_dependencies

exit $?