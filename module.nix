flake: { config, lib, pkgs, ... }:

let
  inherit (lib) filterAttrs foldl imap1 mapAttrsToList mkEnableOption mkIf mkMerge mkOption mkPackageOption types;
  intakeCfg = config.services.intake;
in {
  options = {
    services.intake = {
      listen.addr = mkOption {
        type = types.str;
        default = "0.0.0.0";
        description = "The listen address for the entry point to intake services. This endpoint will redirect to a "
        "local port based on the request's HTTP Basic Auth credentials.";
      };

      listen.port = mkOption {
        type = types.port;
        default = 80;
        description = "The listen port for the entry point to intake services. This endpoint will redirect to a local "
        "port based on the request's HTTP Basic Auth credentials.";
      };

      package = mkPackageOption pkgs "intake" {};

      internalPortStart = mkOption {
        type = types.port;
        default = 24130;
        description = "The first port to use for internal service endpoints. A number of ports will be continguously "
        "allocated equal to the number of users with enabled intake services.";
      };

      extraPackages = mkOption {
        type = types.listOf types.package;
        default = [];
        description = "Extra packages available to all enabled users and their intake services.";
      };

      users = mkOption {
        description = "User intake service definitions.";
        default = {};
        type = types.attrsOf (types.submodule {
          options = {
            enable = mkEnableOption "intake, a personal feed aggregator.";

            extraPackages = mkOption {
              type = types.listOf types.package;
              default = [];
              description = "Extra packages available to this user and their intake service.";
            };
          };
        });
      };
    };
  };

  config =
  let
    # Define the intake package and a python environment to run it from
    intake = intakeCfg.package;
    pythonEnv = pkgs.python38.withPackages (pypkgs: [ intake ]);

    # Assign each user an internal port for their personal intake instance
    enabledUsers = filterAttrs (userName: userCfg: userCfg.enable) intakeCfg.users;
    enabledUserNames = mapAttrsToList (userName: userCfg: userName) enabledUsers;
    userPortList = imap1 (i: userName: { ${userName} = i + intakeCfg.internalPortStart; }) enabledUserNames;
    userPort = foldl (acc: val: acc // val) {} userPortList;

    # To avoid polluting PATH with httpd programs, define an htpasswd wrapper
    htpasswdWrapper = pkgs.writeShellScriptBin "htpasswd" ''
      ${pkgs.apacheHttpd}/bin/htpasswd $@
    '';

    # File locations
    intakeDir = "/etc/intake";
    intakePwd = "${intakeDir}/htpasswd";
  in {
    # Apply the overlay so intake is included in pkgs.
    nixpkgs.overlays = [ flake.overlays.default ];

    # Define a user group for access to the htpasswd file. nginx needs to be able to read it.
    users.groups.intake.members = mkIf (enabledUsers != {}) (enabledUserNames ++ [ "nginx" ]);

    # Define an activation script that ensures that the htpasswd file exists.
    system.activationScripts.etc-intake = ''
      if [ ! -e ${intakeDir} ]; then
        ${pkgs.coreutils}/bin/mkdir -p ${intakeDir};
      fi
      ${pkgs.coreutils}/bin/chown root:root ${intakeDir}
      ${pkgs.coreutils}/bin/chmod 755 ${intakeDir}
      if [ ! -e ${intakePwd} ]; then
        ${pkgs.coreutils}/bin/touch ${intakePwd}
      fi
      ${pkgs.coreutils}/bin/chown root:intake ${intakePwd}
      ${pkgs.coreutils}/bin/chmod 660 ${intakePwd}
    '';

    # Give every intake user the htpasswd wrapper, the shared packages, and the user-specific packages.
    users.users =
    let
      addPackagesToUser = userName: {
        ${userName}.packages =
          [ htpasswdWrapper intake ]
          ++ intakeCfg.extraPackages
          ++ intakeCfg.users.${userName}.extraPackages;
      };
    in mkMerge (map addPackagesToUser enabledUserNames);

    # Enable cron
    services.cron.enable = true;

    # Define a user service for each configured user
    systemd.services =
    let
      runScript = userName: pkgs.writeShellScript "intake-run.sh" ''
        ${pythonEnv}/bin/intake run -d /home/${userName}/.local/share/intake --port ${toString userPort.${userName}}
      '';
      # systemd service definition for a single user, given `services.intake.users.userName` = `userCfg`
      userServiceConfig = userName: userCfg: {
        "intake@${userName}" = {
          description = "Intake service for user ${userName}";
          script = "${runScript userName}";
          path = intakeCfg.extraPackages ++ userCfg.extraPackages;
          serviceConfig = {
            User = userName;
            Type = "simple";
          };
          wantedBy = [ "multi-user.target" ];
          after = [ "network.target" ];
          enable = userCfg.enable;
        };
      };
    in mkMerge (mapAttrsToList userServiceConfig intakeCfg.users);

    # Define an nginx reverse proxy to request auth
    services.nginx = mkIf (enabledUsers != {}) {
      enable = true;
      virtualHosts."intake" = mkIf (enabledUsers != {}) {
        listen = [ intakeCfg.listen ];
        locations."/" = {
          proxyPass = "http://127.0.0.1:$target_port";
          basicAuthFile = intakePwd;
        };
        extraConfig = foldl (acc: val: acc + val) "" (mapAttrsToList (userName: port: ''
          if ($remote_user = "${userName}") {
            set $target_port ${toString port};
          }
        '') userPort);
      };
    };
  };
}
