{ lib
, stdenv
, pkgs
, pythonEnv
, gtk3
, gtk-layer-shell
, gtk-session-lock
, gobject-introspection
, libdbusmenu-gtk3
, gdk-pixbuf
, librsvg
, wayland
, pkg-config
, cinnamon-desktop
, glib
, gnome-bluetooth
, pango
, harfbuzz
, atk
, playerctl
, networkmanager
, pipewire
, upower
, bluez
, brightnessctl
, swayidle
, wlsunset
, wf-recorder
, awww
, gsettings-desktop-schemas
, hicolor-icon-theme
, adwaita-icon-theme
, morewaita-icon-theme
, makeWrapper
, wrapGAppsHook3
}:

let
  # Build libhacktk.so from source — depends on GTK3
  libhacktk = stdenv.mkDerivation {
    pname = "libhacktk";
    version = "0.1.0";
    src = ./snippets/hacktk/lib;

    nativeBuildInputs = [ pkg-config ];
    buildInputs = [ gtk3 ];

    buildPhase = ''
      gcc -fPIC -Wall -Wextra -O2 -shared \
        -o libhacktk.so hacktk.c \
        $(pkg-config --cflags --libs gtk+-3.0) -lm
    '';

    installPhase = ''
      mkdir -p $out/lib
      cp libhacktk.so $out/lib/
    '';
  };

  # Build libblur.so from source — depends on wayland-client
  libblur = stdenv.mkDerivation {
    pname = "libblur";
    version = "0.1.0";
    src = ./snippets/blur/lib;

    nativeBuildInputs = [ pkg-config ];
    buildInputs = [ wayland ];

    buildPhase = ''
      gcc -shared -fPIC -fvisibility=default \
        -o libblur.so blur.c ext-background-effect-v1-protocol.c \
        $(pkg-config --cflags wayland-client) -lwayland-client
    '';

    installPhase = ''
      mkdir -p $out/lib
      cp libblur.so $out/lib/
    '';
  };

  # All runtime libs that provide typelibs
  runtimeLibs = [
    gtk3
    gtk-layer-shell
    gobject-introspection
    gtk-session-lock
    libdbusmenu-gtk3
    gdk-pixbuf
    librsvg
    cinnamon-desktop
    glib
    gnome-bluetooth
    pango
    harfbuzz
    atk
    playerctl
    networkmanager
    upower
  ];

  typelibPath = lib.makeSearchPathOutput "lib" "lib/girepository-1.0" runtimeLibs;
  libraryPath = lib.makeLibraryPath (runtimeLibs ++ [ wayland pipewire ]);

in stdenv.mkDerivation {
  pname = "caffyne-shell";
  version = "0.1.0";
  src = ./.;

  # Native hooks: wrapGAppsHook3 will execute automatically at the end of the build
  nativeBuildInputs = [ makeWrapper wrapGAppsHook3 pkg-config ];
  
  # Keeping these in buildInputs allows wrapGAppsHook3 to harvest and bundle their asset schemas
  buildInputs = runtimeLibs ++ [ 
    wayland 
    gsettings-desktop-schemas
    hicolor-icon-theme
    adwaita-icon-theme
    morewaita-icon-theme
  ];

  dontBuild = true;

  installPhase = ''
    runHook preInstall

    mkdir -p $out/share/caffyne-shell
    cp -r ./* $out/share/caffyne-shell/

    # Patch dlopen paths to point to the Nix store .so locations
    substituteInPlace $out/share/caffyne-shell/snippets/hacktk/hacktk.py \
      --replace-fail \
        'get_relative_path("./lib/libhacktk.so")' \
        '"${libhacktk}/lib/libhacktk.so"'

    substituteInPlace $out/share/caffyne-shell/snippets/blur/blur.py \
      --replace-fail \
        'get_relative_path("./lib/libblur.so")' \
        '"${libblur}/lib/libblur.so"'

    mkdir -p $out/bin
    
    # Python-scoped entry setup wrapper
    makeWrapper ${pythonEnv}/bin/python $out/bin/caffyne-shell \
      --prefix PYTHONPATH : "$out/share/caffyne-shell" \
      --add-flags "$out/share/caffyne-shell/main.py" \
      --chdir "$out/share/caffyne-shell"

    runHook postInstall
  '';

  # We feed wrapGAppsHook3's automation array before it creates the final execution wrapper
  preFixup = ''
    gappsWrapperArgs+=(--set GI_TYPELIB_PATH "${typelibPath}")
    gappsWrapperArgs+=(--set LD_LIBRARY_PATH "${libraryPath}")
    gappsWrapperArgs+=(--set GTK_THEME "Adwaita")
    gappsWrapperArgs+=(--prefix PATH : "${lib.makeBinPath [ pipewire bluez brightnessctl swayidle wlsunset wf-recorder awww ]}")
    
    # Append host runtime schemas so your system-installed application assets resolve natively
    gappsWrapperArgs+=(--suffix XDG_DATA_DIRS : "/run/current-system/sw/share")
    gappsWrapperArgs+=(--suffix XDG_DATA_DIRS : "~/.local/share")
  '';

  meta = {
    description = "A lightweight desktop shell powered by Fabric";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "caffyne-shell";
  };
}
