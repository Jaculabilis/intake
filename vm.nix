{ pkgs, ... }: {
  boot.kernelPackages = pkgs.linuxPackages_latest;

  nixos-shell.mounts = {
    mountHome = false;
    mountNixProfile = false;
    cache = "none";
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
