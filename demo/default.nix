flake: { pkgs, ... }:

{
  system.stateVersion = "22.11";

  nixos-shell.mounts = {
    mountHome = false;
    mountNixProfile = false;
    cache = "none";
  };

  services.intake.users.alpha.enable = true;

  services.intake.users.beta.enable = true;

  users.users.alpha = {
    isNormalUser = true;
    password = "alpha";
  };

  users.users.beta = {
    isNormalUser = true;
    password = "beta";
  };
}
