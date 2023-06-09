flake: { pkgs, ... }:

{
  system.stateVersion = "22.11";

  # Set up two users to demonstrate the user separation
  users.users.alice = {
    isNormalUser = true;
    password = "alpha";
  };

  users.users.bob = {
    isNormalUser = true;
    password = "beta";
  };

  # Put intake on both users' PATH
  environment.systemPackages = [ flake.packages.${pkgs.stdenv.hostPlatform.system}.default ];

  # Set up intake for both users with an entry point at port 8080
  services.intake = {
    listen.port = 8080;
    users.alice.enable = true;
    users.bob.enable = true;
  };

  # Expose the vm's intake revproxy at host port 5234
  virtualisation.forwardPorts = [{
    from = "host";
    host.port = 5234;
    guest.port = 8080;
  }];

  # Mount the demo content for both users
  nixos-shell.mounts = {
    mountHome = false;
    mountNixProfile = false;
    cache = "none";

    extraMounts = {
      "/mnt/alice" = ./alice;
      "/mnt/bob" = ./bob;
      "/mnt/sources" = ./sources;
    };
  };

  # Create an activation script that copies and chowns the demo content
  # chmod 777 because the users may not exist when the activation script runs
  system.activationScripts.demoSetup = ''
    ${pkgs.coreutils}/bin/mkdir -p /home/alice/.local/share/intake
    ${pkgs.coreutils}/bin/cp -r /mnt/alice/* /home/alice/.local/share/intake/
    ${pkgs.coreutils}/bin/chmod -R 777 /home/alice/.local

    ${pkgs.coreutils}/bin/mkdir -p /home/bob/.local/share/intake
    ${pkgs.coreutils}/bin/cp -r /mnt/bob/* /home/bob/.local/share/intake/
    ${pkgs.coreutils}/bin/chmod -R 777 /home/bob/.local
  '';

  # Put the demo sources on the global PATH
  environment.variables.PATH = "/mnt/sources";
}
