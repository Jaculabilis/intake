flake: { pkgs, ... }:

let
  intake = flake.packages.${pkgs.stdenv.hostPlatform.system}.default;

  pythonPkg = pkgs.python38;
  pythonEnv = pythonPkg.withPackages (pypkgs: [ intake ]);

  intakeRun = pkgs.writeShellScript "intake-run.sh" ''
    ${pythonEnv}/bin/intake run -d /home/alpha/.local/share/intake
  '';
in {
  system.stateVersion = "22.11";

  nixos-shell.mounts = {
    mountHome = false;
    mountNixProfile = false;
    cache = "none";
  };

  systemd.services."intake@alpha" = {
    description = "Intake service for user alpha";
    script = "${intakeRun}";
    path = [ ];
    serviceConfig = {
      User = "alpha";
      Type = "simple";
    };
    wantedBy = [ "multi-user.target" ];
    after = [ "network.target" ];
    enable = true;
  };

  services.nginx.enable = true;
  services.nginx.virtualHosts = {
    alpha-fsid = {
      listen = [ { addr = "localhost"; port = 8030; } ];
      locations."/".tryFiles = "/dev/null @dummy";
      locations."@dummy" = {
        return = "200 'this is alpha'";
        extraConfig = ''
          add_header Content-Type text/plain always;
        '';
      };
    };
    beta-fsid = {
      listen = [ { addr = "localhost"; port = 8031; } ];
      locations."/".tryFiles = "/dev/null @dummy";
      locations."@dummy" = {
        return = "200 'youve reached beta'";
        extraConfig = ''
          add_header Content-Type text/plain always;
        '';
      };
    };
    redirector = {
      listen = [ { addr = "localhost"; port = 8032; } ];
      locations."/" = {
        proxyPass = "http://127.0.0.1:$target_port";
        basicAuth = { alpha = "alpha"; beta = "beta"; };
      };
      extraConfig = ''
        if ($remote_user ~ "alpha|^$") {
          set $target_port 8030;
        }
        if ($remote_user = "beta") {
          set $target_port 8031;
        }
      '';
    };
  };

  users.users.alpha = {
    isNormalUser = true;
    password = "alpha";
  };

  users.users.beta = {
    isNormalUser = true;
    password = "beta";
  };
}
