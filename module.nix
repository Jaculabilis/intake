flake: { config, lib, pkgs, ... }:

let
  inherit (lib) mapAttrsToList mkEnableOption mkMerge mkOption types;
  intakeCfg = config.services.intake;
in {
  options = {
    services.intake = {
      listen.addr = mkOption {
        type = types.str;
        default = "0.0.0.0";
        description = "Listen address for the nginx entry point.";
      };

      listen.port = mkOption {
        type = types.port;
        default = 80;
        description = "Listen port for the nginx entry point.";
      };

      users = mkOption {
        description = "User intake service definitions.";
        default = {};
        type = types.attrsOf (types.submodule {
          options = {
            enable = mkEnableOption "intake, a personal feed aggregator.";

            packages = mkOption {
              type = types.listOf types.package;
              default = [];
              description = "Additional packages available to the intake service.";
            };
          };
        });
      };
    };
  };

  config =
  let
    # Define the intake package and a python environment to run it from
    intake = flake.packages.${pkgs.stdenv.hostPlatform.system}.default;
    pythonEnv = pkgs.python38.withPackages (pypkgs: [ intake ]);
  in {
    systemd.services =
    let
      runScript = userName: pkgs.writeShellScript "intake-run.sh" ''
        ${pythonEnv}/bin/intake run -d /home/${userName}/.local/share/intake
      '';
      # systemd service definition for a single user, given `services.intake.users.userName` = `userCfg`
      userServiceConfig = userName: userCfg: {
        "intake@${userName}" = {
          description = "Intake service for user ${userName}";
          script = "${runScript userName}";
          path = userCfg.packages;
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
  };
}
