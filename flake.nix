{
  description = "caffyne-shell — a lightweight desktop shell powered by Fabric";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    utils.url = "github:numtide/flake-utils";
    fabric = {
      url = "github:Fabric-Development/fabric";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, utils, fabric, ... }:
    utils.lib.eachDefaultSystem (system:
      let
        fabricOverlay = final: prev: {
          pythonPackagesExtensions =
            prev.pythonPackagesExtensions
            ++ [
              (python-final: python-prev: {
                python-fabric = prev.callPackage
                  "${fabric}/default.nix" {};
              })
            ];
        };

        pkgs = nixpkgs.legacyPackages.${system}.extend fabricOverlay;

        nativeLibs = with pkgs; [
          gtk3
          glib
          pango
          gtk-layer-shell
          cairo
          gtk-session-lock
          harfbuzz
          atk
          playerctl
          gobject-introspection
          libdbusmenu-gtk3
          gdk-pixbuf
          gnome-bluetooth
          gtk-session-lock
          cinnamon-desktop
          librsvg
          linux-pam
          networkmanager
          pipewire
          upower
          bluez
          brightnessctl
          swayidle
          wlsunset
          wf-recorder
          awww
        ];

        pythonEnv = pkgs.python3.withPackages (ps: with pkgs.python3Packages; [
          python-fabric
          cffi
          click
          loguru
          pillow
          psutil
          pycairo
          pycparser
          pygobject3
          python-pam
          rapidfuzz
          setproctitle
          six
          thefuzz
          setuptools
        ]);

      in {
        formatter = pkgs.nixfmt-rfc-style;

        packages.default = pkgs.callPackage ./package.nix {
          inherit pythonEnv;
          inherit (pkgs)
            gtk3
            gtk-layer-shell
            gobject-introspection
            libdbusmenu-gtk3
            gdk-pixbuf
            librsvg
            wayland
            pkg-config
            cinnamon-desktop
            glib
            gnome-bluetooth
            pango
            harfbuzz
            atk
            playerctl
            networkmanager
            pipewire
            upower
            bluez
            brightnessctl
            swayidle
            wlsunset
            wf-recorder
            awww
            gsettings-desktop-schemas
            hicolor-icon-theme
            adwaita-icon-theme
            morewaita-icon-theme
            makeWrapper
            wrapGAppsHook3;
        };

        devShells.default = pkgs.mkShell {
          name = "caffyne-shell";
          packages = [ pythonEnv pkgs.ruff ] ++ nativeLibs;
          shellHook = ''
            export GI_TYPELIB_PATH=${pkgs.lib.makeSearchPathOutput "lib" "lib/girepository-1.0" nativeLibs}
            export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath nativeLibs}
          '';
        };
      }
    );
}
