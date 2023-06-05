flake: { config, lib, pkgs, ... }:

let
  inherit (lib) mkIf mkOption types;

  cfg = config.services.intake;
in {
  options = {
  };

  config = {
  };
}